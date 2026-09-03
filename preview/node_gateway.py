"""
EXCERPT — src/audio/node.py

Recovering a Lavalink node that has died in a way the client cannot see.

The whole file exists because of one measured fact: wavelink's `node.status`
kept reporting CONNECTED for as long as the node stayed down. Every recovery
path built on that field was a no-op, and the station sat silent while
reporting itself healthy.

Two things follow from that, and both are in here:

  · liveness is PROBED, never read
  · every await is BOUNDED, because the thing being awaited is by definition
    unreachable

Trimmed for reading. Imports and constants elided.
"""


class NodeGateway:
    """Owns the truth about whether the audio node is actually reachable."""

    def __init__(self) -> None:
        self._last_probe_error: Optional[str] = None

        # Result and timing of the most recent active probe. node.status keeps
        # reporting CONNECTED long after the socket dies, so anything that
        # wants the truth reads these, never the status enum.
        self._last_probe_at: Optional[float] = None
        self._last_probe_ok: Optional[bool] = None

    @property
    def last_probe_ok(self) -> Optional[bool]:
        """Last active probe result, or None if none has run yet.

        Tri-state deliberately. The supervisor sleeps a full sweep before its
        first probe, so a plain False would mean "unhealthy" for the first
        thirty seconds of every process — publishing a dead node during
        exactly the restart someone is watching. None means unknown, and a
        caller decides what to do with that.
        """
        return self._last_probe_ok

    async def alive(self) -> bool:
        """Actively probe the node. The ONLY trustworthy liveness signal.

        Costs one cheap REST call. Worth it: the alternative is trusting a
        status field that has been observed lying for as long as the node
        stayed down.
        """
        result = await self._probe()
        self._last_probe_at = time.monotonic()
        self._last_probe_ok = result
        return result

    async def _probe(self) -> bool:
        """The probe itself. Separated so every exit records exactly once —
        recording at each return is how one of them ends up not recording."""
        node = self.node()
        if node is None:
            self._last_probe_error = "No node registered in the pool"
            return False
        try:
            await asyncio.wait_for(
                node.fetch_stats(), timeout=NODE_PROBE_TIMEOUT_S)
            self._last_probe_error = None
            return True
        except asyncio.TimeoutError:
            self._last_probe_error = f"Timeout after {int(NODE_PROBE_TIMEOUT_S)}s"
            return False
        except Exception as e:
            self._last_probe_error = f"{type(e).__name__}: {e}".strip(": ")
            return False

    async def revive(self) -> None:
        """Force the node back up.

        The close() is load-bearing and must come FIRST: `Pool.reconnect()`
        iterates nodes and skips any whose status is not DISCONNECTED, so
        without forcing the state change it silently does nothing at all —
        for exactly the case it is needed in.

        BOUNDED, and that bound is load-bearing too. `Pool.reconnect()` reaches
        wavelink's `Websocket.connect()`, a `while True` that only exits on
        success, on a 401/404, or when `retries` hits zero — and this node is
        built with `retries=None`, so while Lavalink is down it retries
        forever. Awaiting it unbounded parked the supervisor on its first sweep
        for the whole outage: the probe counter froze at one, so the fail-fast
        restart could never fire, and dead-air and stall detection never ran
        either. The timeout returns control to the sweep so those can do their
        job.
        """
        node = self.node()
        if node is not None:
            try:
                # Bounded for the same reason: close() awaits a REST DELETE per
                # player against a node that is by definition unreachable, on a
                # session with aiohttp's 5-minute default timeout. A blackholed
                # node (partition, hung JVM) would park the supervisor for that
                # long — freezing the counter the fail-fast restart depends on.
                await asyncio.wait_for(
                    node.close(eject=False), timeout=NODE_REVIVE_TIMEOUT_S)
            except Exception as e:
                # NOT silent: a failed close means the status may still not be
                # DISCONNECTED, and Pool.reconnect() skips anything that isn't
                # — so the revive below would quietly no-op.
                logger.warning("Lavalink Node Close Failed", [
                    ("Reason", f"{type(e).__name__}: {e}"),
                    ("Status", self.status_name()),
                    ("Impact", "Pool.reconnect() may skip this node"),
                ])

        try:
            await asyncio.wait_for(
                wavelink.Pool.reconnect(), timeout=NODE_REVIVE_TIMEOUT_S)
        except asyncio.TimeoutError:
            # Expected while the node is genuinely down. wavelink keeps
            # retrying in its own task; the sweep just needs to stay alive.
            logger.tree("Lavalink Reconnect Pending", [
                ("Waited", f"{int(NODE_REVIVE_TIMEOUT_S)}s"),
                ("Action", "Returning to the sweep — retry continues in background"),
            ], emoji=LOG_EMOJI_RECONNECT)
        except Exception as e:
            logger.error_tree("Lavalink Reconnect Failed", e, [
                ("Next Sweep", f"{int(SUPERVISOR_INTERVAL_S)}s"),
            ])
