"""
EXCERPT — src/services/api.py and src/services/snapshot.py

The WebSocket the public station page reads.

One rule shapes the whole thing: **a page that blanks during an incident is
worse than one showing a stopped clock.** So the API never returns 5xx. A
failure answers 200 with the last good payload, `ok: false`, and an honest
`generated_at` — and the page has a designed state for exactly that.

Trimmed for reading. Routing, lifecycle and imports elided.
"""


class StationAPI:
    """Serves the snapshot over a WebSocket, and once over plain GET."""

    def snapshot(self) -> Dict[str, Any]:
        """A fresh payload, or the last good one marked stale."""
        try:
            payload = self.builder.build()
        except Exception as e:
            self._degraded = True
            self._report("Snapshot Build Failed", e, [
                ("Action", "Serving the last good payload as stale"),
                ("Have Fallback", str(self._last_good is not None)),
            ])
            return self._stale()

        if self._degraded:
            self._degraded = False
            # Recovery gets a line too. Without one you can watch it break and
            # never watch it heal — the throttle hides the next 300s of errors,
            # so silence afterwards is indistinguishable from still-broken.
            logger.tree("Snapshot Recovered", [
                ("Action", "Serving fresh payloads again"),
            ], emoji=LOG_EMOJI_API)

        self._last_good = payload
        return payload

    def _encoded(self) -> bytes:
        """Snapshot, serialized. Encoding lives inside the failure guard on
        purpose: json.dumps runs synchronously, so a value it can't handle
        would otherwise escape the handler and become the 500 this service
        promises never to return."""
        try:
            return json.dumps(self.snapshot()).encode()
        except (TypeError, ValueError) as e:
            self._report("Snapshot Encode Failed", e, [
                ("Action", "Serving the empty payload"),
            ])
            return json.dumps(empty_snapshot()).encode()

    async def _push_forever(self) -> None:
        """Serialize once per tick and fan the same bytes out to every client.

        Once, not per client: the snapshot and its encoding are the expensive
        half, and doing either per socket would make cost scale with audience
        for identical bytes.
        """
        while True:
            await asyncio.sleep(API_PUSH_INTERVAL_S)
            if not self._clients:
                continue

            body = self._encoded()
            # Snapshot the set: a client disconnecting mid-fan-out mutates
            # it, and iterating a set while it changes raises.
            targets = tuple(self._clients)
            results = await asyncio.gather(
                *[self._send(ws, body) for ws in targets],
                return_exceptions=True,
            )
            await self._drop_failed(targets, results)

    async def _drop_failed(self, targets, results) -> None:
        """Evict every client whose frame failed.

        Results are positionally aligned with targets — that alignment is the
        point. Counting failures without using it leaves a wedged client in
        the set, drawing a dropped frame every tick until the heartbeat
        eventually reaps it.
        """
        for ws, result in zip(targets, results):
            if result is None:
                continue
            self._clients.discard(ws)
            await self._close(ws)


class SnapshotBuilder:
    """Reads the live station and renders one payload.

    Pure reads of live objects: never touches Lavalink, never awaits, never
    mutates — so it can be called from a socket push without racing the
    playback loop.
    """

    def build(self) -> Dict[str, Any]:
        """The full payload. Always succeeds — every section degrades to a
        null or a zero rather than raising, because a snapshot that can throw
        is a snapshot that blanks the page during exactly the incident it
        exists to describe."""
        now = time.monotonic()
        station = self.station
        player = station.player
        playing = station.is_playing

        # Each resolved once and passed down: two lookups for one channel, or
        # two clock reads for one instant, are two chances to disagree inside
        # a single payload.
        stamp = utc_now()
        channel = resolve_voice_channel(station.bot, station.cfg.VOICE_CH)
        current = getattr(player, "current", None)
        current_stem = display_name(current) if current is not None else None

        return {
            "ok": True,
            "stale": False,
            "served_at": stamp,
            "generated_at": stamp,
            "playing": playing,
            "track": self._track(player, current, current_stem),
            "listeners": listener_count(channel),
            "channel": {
                # A string: a snowflake exceeds what JSON numbers hold exactly.
                "id": str(station.cfg.VOICE_CH),
                "name": getattr(channel, "name", None),
            },
            "deck": self._deck(current_stem),
            "node": self._node(),
            "dead_air_s": self._dead_air(playing, now),
            "lifetime_minutes_played": self.playtime.minutes,
            # ... status line, uptime, fader settings
        }

    def _node(self) -> Dict[str, Any]:
        gateway = self.station.node
        age = gateway.last_probe_age_s
        return {
            # None until the first probe — unknown, not unhealthy. The probe
            # error string is deliberately NOT published: it embeds the node's
            # host and port.
            "healthy": gateway.last_probe_ok,
            "lavalink": LAVALINK_PROTOCOL_VERSION,
            "last_probe_s_ago": round(age, 1) if age is not None else None,
            "consecutive_failures": self.station.health.probe_failures,
        }
