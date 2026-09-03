<div align="center">

<img src="assets/logo.png" width="120" alt="Mazaj">

# مزاج · Mazaj

**A 24/7 ambient Arabic lo-fi station, living in one Discord voice channel.**

Six hours of Fairuz, George Wassouf, Kadim Al Saher and Elissa, on a shuffle
that never stops, for [discord.gg/syria](https://discord.gg/syria).

<img src="assets/divider.png" width="420" alt="">

`Python 3.12` · `discord.py` · `Lavalink` · `WebSocket` · `React` · `TypeScript`

**[Live station page →](https://trippixn.com/Mazaj)**

</div>

<img src="assets/divider.png" width="100%" alt="">

## This is a preview, not the source

Mazaj is a private bot for one server. This repository exists to show the
engineering and the design behind it — the architecture, the failure modes that
shaped it, the pieces I'm proud of. The bot itself, its token, its audio library
and its production configuration are not here and will not be.

Everything quoted below is real code from the running system.

<img src="assets/divider.png" width="100%" alt="">

## What it actually does

A station bot sounds trivial: join a channel, play a file, loop. The interesting
part is everything that happens when that simple loop meets a real network.

| | |
|---|---|
| **Never stops** | Resumes mid-track across restarts, rebuilds its own voice connection, and force-restarts itself when its audio node dies in a way it cannot recover from |
| **Never silently fails** | A bot with no commands and no chat is invisible when it breaks — so every subsystem reports into a structured log tee'd to Discord |
| **Live control panel** | A Components V2 card with a gold progress bar, a running timer and a track selector. It follows the conversation, re-posting below whatever was last said |
| **Public API** | A loopback WebSocket publishes the station's live state; a React page renders it |
| **Listener stats** | Per-person listening time, accumulated across restarts, with join and leave cards |

```
 ~8,600 lines Python        ~6,100 lines TypeScript
 22 modules                 6 audio tracks · 497 MB
 0 slash commands           1 dropdown
```

<img src="assets/divider.png" width="100%" alt="">

## Architecture

```
                    ┌───────────────────────────┐
   Discord ◄───────►│         MazajBot          │
   Gateway          │                           │
                    │  ┌─────────────────────┐  │
                    │  │ Station             │  │──► Lavalink (JVM)
                    │  │  · voice connection │  │    decodes + encodes
                    │  │  · shuffle deck     │  │    audio out of process
                    │  │  · supervisor sweep │  │
                    │  │  · volume fader     │  │
                    │  └─────────────────────┘  │
                    │  ┌─────────────────────┐  │
                    │  │ Services            │  │
                    │  │  panel · presence   │  │
                    │  │  greeter · tracker  │  │
                    │  │  banner · purge     │  │
                    │  └─────────────────────┘  │
                    │  ┌─────────────────────┐  │
                    │  │ Station API :8092   │──┼──► nginx ──► trippixn.com/Mazaj
                    │  │  WebSocket, 5s push │  │             (React + Vite)
                    │  └─────────────────────┘  │
                    └───────────────────────────┘
```

**Audio is out of process.** Lavalink reads the files off disk and does the
Opus encoding; the bot only ever says *which* file. That is what keeps a Python
process with a dozen background loops from ever being in the audio path.

**Minimum privilege.** No `message_content`, no `members` intent. The bot knows
somebody spoke; it cannot read a word of it.

<img src="assets/divider.png" width="100%" alt="">

## Four problems worth writing down

The parts of this project I'd actually want to talk about in an interview.

### 1. The node lies about being alive

wavelink exposes `node.status`. During a real Lavalink outage it kept reporting
`CONNECTED` long after the socket was dead — so every recovery path built on it
was a no-op, and the station sat silent while claiming to be healthy.

The fix was to stop asking and start probing:

```python
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
```

That result is tri-state, not boolean. `None` means *not yet probed* — because
the supervisor sleeps a full sweep before its first check, and a plain `False`
there meant the API reported a healthy station as stopped for the first thirty
seconds of every restart. Which is exactly the half-minute somebody watching a
recovery is looking at.

### 2. A wait that never waits

The control panel follows chat: post a message, the panel re-posts below it. A
six-second floor stops a burst of chat becoming a delete-and-repost per line.

The bug was in how the loop slept:

```python
await asyncio.wait_for(self._activity.wait(), timeout=delay)
```

`asyncio.Event.wait()` on an already-set event returns **immediately**, and the
event was only cleared when a move actually happened. So during the floor —
exactly when the code believed it was throttling — the loop spun, editing the
panel at whatever rate the rate-limiter allowed. On an unresolvable channel it
spun with *no await at all*, blocking the entire event loop, audio included.

One event was doing two jobs. Splitting them fixed it:

```python
# Two separate things, deliberately. The Event is EDGE-triggered: it
# exists only to wake the tick early and is consumed once per pass.
# _pending_move is the LEVEL state that survives the sticky floor.
self._activity: asyncio.Event = asyncio.Event()
self._pending_move: bool = False
```

Measured after: **1 pass in 6 seconds**, down from thousands.

### 3. A backoff is a deadline, not a hint

Same loop, second lesson. On failure the tick computes a 60-second backoff —
then waits on the activity event, which any chat message sets. So a single
message would cut a 60-second backoff to nothing and immediately retry the
operation that had just failed. When the failure involved the banner, that retry
re-uploaded 7.6 MB. Per message.

```python
# A failure backoff is a deadline, not a hint. Chat must not shorten
# it: _activity is cleared each pass, so ANY message would otherwise
# make the wait return instantly and retry the operation that just
# failed — and when the banner url has been dropped that retry
# re-uploads 7.6MB, once per message.
if delay > PANEL_TICK_S:
    await asyncio.sleep(delay)
    return
```

### 4. Two clocks, one number

Listening time is credited in intervals, and any interval longer than 90 seconds
is discarded — a suspended process is not somebody listening. The per-visit
figure was measured differently: wall-clock, from a start stamp, with no such
clamp.

Nobody notices that until a stall, and then a farewell card reads:

> This session · `6h 12m` (`2m` total)

A visit longer than the lifetime containing it. The fix wasn't a clamp bolted on
— it was making the two numbers structurally incapable of disagreeing:

```python
if 0 < elapsed <= VOICE_TRACK_MAX_TICK_GAP_S:
    self._totals[user_id] = self._totals.get(user_id, 0.0) + elapsed
    # Same interval, same clamp, same branch. Feeding the session
    # from anywhere else is how it grew larger than the lifetime
    # total that contains it.
    self._session[user_id] = self._session.get(user_id, 0.0) + elapsed
```

Verified over 500 randomized syncs: 2,334 sessions recorded, zero violations of
`session ≤ total`.

<img src="assets/divider.png" width="100%" alt="">

## Observability, because there is nothing else

Mazaj has no commands. It says nothing in chat. If it breaks, the only way to
find out is the log — so the log is treated as a product surface, not debris.

```
[08:34:11 AM EDT] 🔊 Voice Tracker Loaded
  ├─ File: data/voice_time.json
  ├─ Source: Existing
  ├─ Listeners: 8
  ├─ Total: 2h 59m 9s
  └─ Since: 2026-09-03T10:45:30Z
```

Structured, tee'd to Discord webhooks, with a per-session run ID on every line.

The subtlety is that a log which floods is a log that is off. Certain glyphs
route to an error webhook, and a durable fault inside a loop that ticks forever
will hit Discord's rate limiter and take the whole feed down with it — so every
repeating report goes through a throttle whose window must be **longer than the
tick that drives it**:

```python
class ThrottledReporter:
    """A LogThrottle plus the "Suppressed" row, for loops that tick forever.

    The window MUST be longer than the loop's tick. A window equal to the
    tick suppresses nothing, and an unthrottled error in a forever-loop
    reports at the tick rate until it trips the logger's own 429 breaker and
    takes the whole webhook tee offline.
    """
```

<img src="assets/divider.png" width="100%" alt="">

## Design

<div align="center">
<img src="assets/mazaj_logo.png" width="72"> &nbsp;
<img src="assets/duration_gold.png" width="72"> &nbsp;
<img src="assets/github_gold.png" width="72"> &nbsp;
<img src="assets/terms_gold.png" width="72"> &nbsp;
<img src="assets/privacy_gold.png" width="72">
</div>

Every glyph is generated, not downloaded — rendered headless at 4× and
downsampled, on a six-stop gold ramp with a clipped inner bevel:

- **A single top-to-bottom ramp between two yellows has no light source in it.**
  That is why the first pass read as mustard. Real gold needs a near-white
  specular and a deep bronze, on a diagonal.
- **The shadow must be warm.** A cool shadow under warm metal is the tell that
  makes a render look like a yellow sticker.
- **Detail is cut out, not drawn on.** Holes stay as legible as the shape around
  them; painted-on detail is the first thing to vanish at 24px.
- **Fill the canvas.** Discord cannot scale an emoji up, so internal padding is
  the only reason a glyph ever reads small. Everything is cropped and re-padded
  to 92%.

The progress bar is six custom emoji — rounded end caps and a repeating middle,
so it reads as a bar rather than a row of blocks. It is deliberately *not*
wrapped in backticks: custom emoji do not render inside inline code, a detail
that cost a redesign to discover.

<img src="assets/divider.png" width="100%" alt="">

## The station page

`trippixn.com/Mazaj` renders live state from a WebSocket the bot serves on
loopback, proxied same-origin so the site's `connect-src 'self'` CSP is untouched.

It is built around a rule: **a page that blanks during an incident is worse than
one showing a stopped clock.** The API therefore never returns 5xx — a failure
answers `200` with the last good payload, `ok: false`, and an honest
`generated_at`. The page renders four designed states off that contract:

| State | Meaning |
|---|---|
| **On air** | Amber, playhead advancing |
| **Last heard** | Values hold but drain from amber to sage; the clock stops rather than being extrapolated |
| **Off air** | Bot down, API up — the dead-air timer becomes the loudest number on the panel |
| **No answer** | Every band and label stays, all values render as dashes |

The playhead interpolates on the rail — a continuous quantity — and never
interpolates the clock, which is a sampled fact.

<img src="assets/divider.png" width="100%" alt="">

## Stack

**Bot** — Python 3.12, discord.py 2.7 (pinned under 2.8; its new voice backend
breaks streaming), wavelink 3.5 against Lavalink v4, aiohttp. No database: state
lives in small atomic JSON sidecars, because nothing here needs more.

**Page** — React, TypeScript, Vite, Tailwind, Framer Motion.

**Infra** — a single Hetzner box, systemd, nginx. Lavalink runs as its own
service and is shared with a sibling bot.

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

Built by **Trippixn** · [trippixn.com](https://trippixn.com) · [discord.gg/syria](https://discord.gg/syria)

<img src="assets/divider.png" width="420" alt="">

<sub>Mazaj is a private bot. This repository is a preview of its engineering and design.</sub>

</div>
