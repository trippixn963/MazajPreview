<div align="center">

<img src="assets/logo.png" width="110" alt="Mazaj">

# مزاج · Mazaj

**A 24/7 ambient Arabic lo-fi station, living in one Discord voice channel.**

<img src="assets/divider.png" width="420" alt="">

`Python 3.12` · `discord.py` · `Lavalink` · `WebSocket` · `React`

**[Live station page →](https://trippixn.com/Mazaj)**

</div>

<img src="assets/divider.png" width="100%" alt="">

Mazaj is a private bot for [discord.gg/syria](https://discord.gg/syria). This
repo is a preview of the engineering and design — not the source, which stays
private. Every snippet below is verbatim from the running system.

```
~8,600 lines Python     ~6,100 lines TypeScript
0 slash commands        6 tracks · 497 MB · always on
```

It resumes mid-track across restarts, rebuilds its own voice connection, and
restarts itself when its audio node dies unrecoverably. A Components V2 panel
follows the conversation. A loopback WebSocket feeds the public station page.

**Audio is out of process** — Lavalink does the decoding and Opus encoding; the
bot only says *which* file. **Minimum privilege** — no `message_content`, no
`members` intent. It knows somebody spoke; it can't read a word.

<img src="assets/divider.png" width="100%" alt="">

## Two problems worth writing down

**The node lied about being alive.** wavelink's `node.status` kept reporting
`CONNECTED` long after the socket died — so every recovery path built on it was
a no-op while the station sat silent claiming health. Fixed by probing instead
of asking, and making the answer tri-state: `None` means *not yet probed*, which
stopped a fresh restart reporting a healthy station as stopped.

**A wait that never waited.** The panel re-posts below new messages, floored at
six seconds. But `asyncio.Event.wait()` on an already-set event returns
immediately — so during the floor, exactly when the code believed it was
throttling, the loop spun and edited the panel at rate-limiter speed. On an
unresolvable channel it spun with no `await` at all, blocking the event loop,
audio included. One event was doing two jobs:

```python
# Two separate things, deliberately. The Event is EDGE-triggered: it
# exists only to wake the tick early and is consumed once per pass.
# _pending_move is the LEVEL state that survives the sticky floor.
self._activity: asyncio.Event = asyncio.Event()
self._pending_move: bool = False
```

Measured after: **1 pass in 6 seconds**, down from thousands.

<img src="assets/divider.png" width="100%" alt="">

## Observability, because there is nothing else

No commands, no chat. If it breaks, the log is the only way to know — so it's
treated as a product surface, tee'd to Discord with a per-session run ID.

```
[08:34:11 AM EDT] 🔊 Voice Tracker Loaded
  ├─ Source: Existing
  ├─ Listeners: 8
  └─ Total: 2h 59m 9s
```

The subtlety: a log that floods is a log that's off. Every repeating report goes
through a throttle whose window must be **longer than the tick driving it**,
or a durable fault trips Discord's rate limiter and takes the whole feed down.

<img src="assets/divider.png" width="100%" alt="">

## Code

Four annotated excerpts, verbatim from the running bot. Trimmed to read
standalone — they won't run.

| | |
|---|---|
| [`node_gateway.py`](preview/node_gateway.py) | Probing a node that lies about being alive. Every await bounded, because the thing being awaited is by definition unreachable |
| [`panel_loop.py`](preview/panel_loop.py) | The sticky panel's tick, the busy-spin that lived in it, and why a backoff is a deadline |
| [`primitives.py`](preview/primitives.py) | Three small pieces the bot leans on — each written two or three times first, then unified |
| [`station_api.py`](preview/station_api.py) | The WebSocket behind the station page, built so it can never return 5xx |

<img src="assets/divider.png" width="100%" alt="">

## Design

<div align="center">
<img src="assets/mazaj_logo.png" width="64"> &nbsp;
<img src="assets/duration_gold.png" width="64"> &nbsp;
<img src="assets/github_gold.png" width="64"> &nbsp;
<img src="assets/terms_gold.png" width="64"> &nbsp;
<img src="assets/privacy_gold.png" width="64">
</div>

Every glyph is generated — headless at 4×, downsampled, six-stop gold ramp with
a clipped inner bevel.

- **A ramp between two yellows has no light source in it.** That's why the first
  pass read as mustard: real gold needs a near-white specular and a deep bronze,
  on a diagonal.
- **The shadow must be warm.** A cool shadow under warm metal is the tell that
  makes a render look like a yellow sticker.
- **Detail is cut out, not drawn on.** Holes stay legible at 24px; painted-on
  detail is the first thing to vanish.

The station page never returns 5xx — a failure answers `200` with the last good
payload and an honest `generated_at`, because a page that blanks during an
incident is worse than one showing a stopped clock.

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

Built by **Trippixn** · [trippixn.com](https://trippixn.com) · [discord.gg/syria](https://discord.gg/syria)

<sub>Private bot. This repository is a preview of its engineering and design.</sub>

</div>
