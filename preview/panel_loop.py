"""
EXCERPT — src/audio/panel.py

The sticky control panel's tick loop, and the bug that lived in it.

The panel follows the conversation: post a message in the channel and it
re-posts itself below you. A six-second floor stops a burst of chat becoming a
delete-and-repost per line.

The floor worked. The SLEEP did not — see _wait_next. Two separate failures
came out of one `asyncio.Event` doing two jobs, and both are documented in
place because the fix only looks obvious once you know what it cost.

Trimmed for reading. Imports, rendering and error handling elided.
"""


class PanelService:
    """Keeps one live panel message at the bottom of the station channel."""

    def __init__(self, bot, station) -> None:
        # Two separate things, deliberately. The Event is EDGE-triggered: it
        # exists only to wake the tick early and is consumed once per pass.
        # _pending_move is the LEVEL state that survives the sticky floor.
        #
        # They were one Event, and that was a bug: Event.wait() on a set event
        # returns instantly, so every tick that declined to move — the floor,
        # a failed send, a backoff — became a zero-second sleep and the loop
        # re-edited the panel at whatever rate the bucket allowed.
        self._activity: asyncio.Event = asyncio.Event()
        self._pending_move: bool = False
        self._moved_at: float = 0.0

    def note_activity(self) -> None:
        """Somebody posted in the channel — the panel is no longer last.

        Only records the fact. The move happens on the panel's own tick, so a
        chat burst coalesces into one relocation rather than racing the
        message handler and posting a panel per line.
        """
        self._activity.set()

    def _should_move(self) -> bool:
        """Whether this tick should relocate the panel to the bottom."""
        if not self._pending_move or self._message is None:
            return False
        return (time.monotonic() - self._moved_at) >= PANEL_STICKY_MIN_INTERVAL_S

    async def start(self) -> None:
        """Tick the panel until shutdown."""
        while not self._stopping:
            # Consumed HERE, once per pass, so the Event is clear by the time
            # the loop waits on it again. Leaving it set is what turned a
            # declined move into a zero-second sleep.
            if self._activity.is_set():
                self._activity.clear()
                self._pending_move = True

            try:
                # The return value is what makes a failed CREATE back off —
                # creating the panel uploads the banner, and retrying that at
                # full tick rate would re-send megabytes every few seconds.
                delay = PANEL_TICK_S if await self.refresh() else PANEL_FAILURE_DELAY_S
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._report("Panel Tick Failed", e, [("Action", "Panel continues")])
                delay = PANEL_FAILURE_DELAY_S

            await self._wait_next(delay)

    async def _wait_next(self, delay: float) -> None:
        """Sleep until the next tick, or until somebody speaks.

        A move still waiting on the sticky floor shortens the sleep to when
        the floor opens, so the panel lands as soon as it legally can rather
        than at the end of a full refresh period.
        """
        # A failure backoff is a deadline, not a hint. Chat must not shorten
        # it: _activity is cleared each pass, so ANY message would otherwise
        # make the wait return instantly and retry the operation that just
        # failed — and when the banner url has been dropped that retry
        # re-uploads 7.6MB, once per message.
        if delay > PANEL_TICK_S:
            await asyncio.sleep(delay)
            return

        if self._pending_move and self._message is not None:
            remaining = PANEL_STICKY_MIN_INTERVAL_S - (
                time.monotonic() - self._moved_at)
            # Floored: a deadline already passed must still yield to the loop
            # rather than become a zero-length sleep.
            await asyncio.sleep(min(delay, max(remaining, PANEL_MIN_SLEEP_S)))
            return

        try:
            await asyncio.wait_for(self._activity.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _relocate(self, channel, view, gif_path) -> None:
        """Re-post the panel below whatever was said, then bin the old one.

        Post BEFORE delete, deliberately. The other order leaves the channel
        with no panel at all if the send fails, and a failed send is exactly
        what a rate limit looks like — so the failure mode would be "the panel
        vanishes when the channel is busiest".
        """
        old, old_view = self._message, self._view

        # Stamped BEFORE the send, not after. A send that raises must still
        # close the floor: otherwise the caller wakes instantly, the floor is
        # already open, and one failure becomes a retry storm at bucket rate.
        self._moved_at = time.monotonic()

        self._message = await channel.send(
            view=view, files=..., allowed_mentions=PANEL_NO_PINGS)

        self._pending_move = False
        self._view = view

        # Deregister the outgoing view. send() registers each new view in the
        # client's ViewStore under its message id, and NOTHING removes it:
        # delete() does not, the delete event does not, and timeout=None means
        # it never expires. Left alone, a relocation every six seconds orphans
        # a ControlPanel plus its 25 select options ~14,000 times a day.
        if old_view is not None:
            old_view.stop()

        if old is not None:
            try:
                await old.delete()
            except discord.NotFound:
                pass  # Someone beat us to it; the new panel is already up.
