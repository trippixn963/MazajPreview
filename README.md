<div align="center">

<img src="assets/logo.png" width="112" alt="Mazaj">

# مزاج · Mazaj

**A 24/7 ambient Arabic lo-fi station, living in one Discord voice channel.**

Six hours of Fairuz, George Wassouf, Kadim Al Saher and Elissa, on a shuffle
that never stops — for a **10,700-member** community.

<img src="assets/divider.png" width="440" alt="">

`Python 3.12` &nbsp;·&nbsp; `discord.py` &nbsp;·&nbsp; `Lavalink` &nbsp;·&nbsp; `WebSocket` &nbsp;·&nbsp; `React` &nbsp;·&nbsp; `TypeScript`

**[Live station page →](https://trippixn.com/Mazaj)**

</div>

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

Mazaj is a private bot for [discord.gg/syria](https://discord.gg/syria). This is
a preview of how it's built — the source, its configuration and its audio stay
private. Every code excerpt below is verbatim from the running system.

**~8,600 lines Python** · **~6,100 lines TypeScript** · 22 modules · zero slash commands

</div>

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

|  |  |  |
|:-:|:-:|:-:|
| <img src="assets/tile-panel.png" width="290"> | <img src="assets/tile-selector.png" width="290"> | <img src="assets/tile-profile.png" width="290"> |
| **The panel** — gold progress bar, running timer, and the last person to change the track | **The library** — bilingual labels and real durations, one swap per person every ten minutes | **The profile** — banner mirrored from a live server-stats render shared with a sibling bot |

|  |  |
|:-:|:-:|
| <img src="assets/tile-welcome.png" width="450"> | <img src="assets/tile-status.png" width="450"> |
| **Arrivals** — mentioned on the way in, never on the way out. Self-deletes after ten minutes | **Status and presence** — sixteen bilingual mood lines, mirrored so the two can never drift |

</div>

<img src="assets/divider.png" width="100%" alt="">

## <img src="assets/icon-bolt.png" width="22" align="top"> &nbsp;How it works

```
                  ┌─────────────────────────┐
  Discord ◄──────►│        MazajBot         │
  Gateway         │                         │
                  │  Station                │──► Lavalink (JVM)
                  │   voice · deck · fader  │    decodes + encodes
                  │   supervisor sweep      │    out of process
                  │                         │
                  │  Services               │
                  │   panel · presence      │
                  │   greeter · tracker     │
                  │                         │
                  │  API :8092  ◄───────────┼──► nginx ──► trippixn.com/Mazaj
                  │   WebSocket, 5s push    │              React + Vite
                  └─────────────────────────┘
```

A supervisor sweeps every 30 seconds: probes the audio node, watches for a
stalled playhead, and detects dead air. State lives in small atomic JSON
sidecars — no database, because nothing here needs one.

**Minimum privilege.** No `message_content`, no `members` intent. The bot knows
somebody spoke; it cannot read a word of it.

<img src="assets/divider.png" width="100%" alt="">

## <img src="assets/icon-terminal.png" width="22" align="top"> &nbsp;Engineering notes

Two failure modes caught in production, and the fixes that hold now. Both are
the kind of bug that reports itself as healthy, which is why they're worth
writing down.

**The node lied about being alive.** During a real Lavalink outage,
`node.status` kept reporting `CONNECTED` long after the socket died — so every
recovery path built on it was a no-op while the station sat silent claiming
health. Fixed by probing instead of asking:

```python
async def alive(self) -> bool:
    """Actively probe the node. The ONLY trustworthy liveness signal.

    Costs one cheap REST call. Worth it: the alternative is trusting a
    status field that has been observed lying for as long as the node
    stayed down.
    """
```

The result is **tri-state**. `None` means *not yet probed*, because the
supervisor sleeps a full sweep before its first check — and a plain `False`
there reported a healthy station as stopped for the first thirty seconds of
every restart, which is exactly the half-minute someone watching a recovery is
looking at.

**A wait that never waited.** The panel follows chat, floored at six seconds so
a burst doesn't become a delete-and-repost per line. `asyncio.Event.wait()` on
an already-set event returns **immediately** — and the event was only cleared
when a move actually happened. So during the floor, exactly when the code
believed it was throttling, the loop spun and edited the panel at rate-limiter
speed. On an unresolvable channel it spun with *no await at all*, blocking the
event loop, audio included. One event was doing two jobs:

```python
# Two separate things, deliberately. The Event is EDGE-triggered: it
# exists only to wake the tick early and is consumed once per pass.
# _pending_move is the LEVEL state that survives the sticky floor.
self._activity: asyncio.Event = asyncio.Event()
self._pending_move: bool = False
```

Measured after: **1 pass in 6 seconds**, down from thousands.

<img src="assets/divider.png" width="100%" alt="">

## <img src="assets/icon-bars.png" width="22" align="top"> &nbsp;The station page

`trippixn.com/Mazaj` renders live state from a WebSocket the bot serves on
loopback, proxied same-origin so the site's `connect-src 'self'` CSP is untouched.

One rule shapes it: **a page that blanks during an incident is worse than one
showing a stopped clock.** So the API never returns 5xx — a failure answers `200`
with the last good payload, `ok: false`, and an honest `generated_at`. Four
designed states read off that contract:

| | |
|:--|:--|
| **On air** | Amber, playhead advancing |
| **Last heard** | Values hold but drain amber → sage; the clock stops rather than being extrapolated |
| **Off air** | Bot down, API up — the dead-air timer becomes the loudest number on the panel |
| **No answer** | Every band and label stays; all values render as dashes |

<img src="assets/divider.png" width="100%" alt="">

## <img src="assets/icon-note.png" width="22" align="top"> &nbsp;Design

Every glyph is generated, not downloaded — rendered headless at 4× and
downsampled, on a six-stop gold ramp with a clipped inner bevel.

- **A ramp between two yellows has no light source in it** — which is why the
  first pass read as mustard. Gold needs a near-white specular and a deep
  bronze, on a diagonal.
- **The shadow must be warm.** A cool shadow under warm metal is the tell that
  makes a render look like a yellow sticker.
- **Detail is cut out, not drawn on.** Holes stay legible at 24px; painted-on
  detail is the first thing to vanish.
- **Fill the canvas.** Discord can't scale an emoji up, so internal padding is
  the only reason a glyph ever reads small — all cropped and re-padded to 92%.

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

Built by **Trippixn** &nbsp;·&nbsp; [trippixn.com](https://trippixn.com) &nbsp;·&nbsp; [discord.gg/syria](https://discord.gg/syria)

<img src="assets/divider.png" width="440" alt="">

<sub>Mazaj is a private bot. This repository is a preview — the source, its configuration and its audio library are not published.</sub>

</div>
