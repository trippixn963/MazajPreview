"""
EXCERPT — src/core/helpers.py and src/core/logger.py

Three small pieces the whole bot leans on. Each exists because the obvious
version was written two or three times first, and the copies drifted.

Trimmed for reading. Imports elided.
"""


class ShuffleDeck(Generic[T]):
    """Draws from a shuffled deck, refilling when exhausted.

    A deck rather than repeated `random.choice` so every item appears once
    per pass — random picking visibly repeats and makes a small set look even
    smaller. On refill, an item matching `last` is moved off the top so a
    reshuffle can't replay whatever just finished.
    """

    __slots__ = ("_source", "_key", "_deck", "_pass", "_dealt")

    @property
    def has_dealt(self) -> bool:
        """Whether anything has been drawn since the deck was last filled.

        An empty `_deck` is ambiguous on its own: it means either "the pass
        is exhausted" or "the pass has not been dealt yet". Reading the
        emptiness literally reports a freshly refilled deck as fully spent —
        which is what a library reload looks like from the outside, and is how
        the station page briefly showed every track as already played.
        """
        return self._dealt

    def draw(self, last: Optional[T] = None) -> Optional[T]:
        """Next item, or None when there's nothing to draw from."""
        if not self._source:
            return None

        if not self._deck:
            self._deck = list(self._source)
            self._pass += 1
            random.shuffle(self._deck)
            if len(self._deck) > 1 and last is not None:
                if self._key(self._deck[-1]) == self._key(last):
                    self._deck.insert(0, self._deck.pop())

        self._dealt = True
        return self._deck.pop()


class Cooldown:
    """Per-key cooldown over an LRU-bounded map.

    Check and commit are SEPARATE calls, deliberately. A throttle that does
    both at once spends the window on an action that then failed — a user
    rate-limited for a message that never sent.

    `max_keys` is required, not optional: every key here is a user id, so the
    map is externally controlled and must not grow with each person the bot
    ever sees.

    Written twice before this existed — the panel's track-swap cooldown and
    the greeter's — with the second carrying a comment saying it mirrored the
    first, which is a duplication documenting itself instead of going away.
    """

    __slots__ = ("_window_s", "_max_keys", "_at")

    def remaining(self, key: Any) -> float:
        """Seconds still to wait, or 0.0 if this key may go now."""
        last = self._at.get(key)
        if last is None:
            return 0.0
        return max(0.0, self._window_s - (time.monotonic() - last))

    def note(self, key: Any) -> None:
        """Start the window — call only after the action actually succeeded."""
        self._at[key] = time.monotonic()
        self._at.move_to_end(key)
        while len(self._at) > self._max_keys:
            self._at.popitem(last=False)  # evict least-recently-used


class ThrottledReporter:
    """A LogThrottle plus the "Suppressed" row, for loops that tick forever.

    Every long-running service needs the same three lines around a throttle:
    record, bail on None, prepend a count. That shape had been written out
    four separate times — two of the copies carrying a comment saying they
    mirrored another — which is the codebase documenting a duplication
    instead of removing it.

    The window MUST be longer than the loop's tick. A window equal to the
    tick suppresses nothing, and an unthrottled error in a forever-loop
    reports at the tick rate until it trips the logger's own 429 breaker and
    takes the whole webhook tee offline.
    """

    def report(self, title, error=None, rows=None, *, emoji=None, key=None) -> bool:
        """Log once per window per key. True if it emitted."""
        count = self._throttle.record(key or title, time.monotonic())
        if count is None:
            return False

        # Copied, never mutated in place: callers pass literals today, and a
        # caller that reuses its list would otherwise grow a Suppressed row
        # per emit.
        out = list(rows or [])
        if count > 1:
            out.insert(0, (
                "Suppressed",
                f"{count - 1} more in last {int(self._window_s)}s",
            ))

        if emoji is None:
            logger.error_tree(title, error, out)
        elif emoji in Logger.ERROR_EMOJIS:
            logger.warning(title, out)
        else:
            logger.tree(title, out, emoji=emoji)
        return True
