<div align="center">

<img src="assets/logo.png" width="112" alt="Mazaj">

# مزاج · Mazaj

**A 24/7 ambient Arabic lo-fi station, living in one Discord voice channel.**

Six hours of Fairuz, George Wassouf, Kadim Al Saher and Elissa, on a shuffle
that never stops — for a **10,700-member** community.

<img src="assets/divider.png" width="440" alt="">

<p>
<img src="https://img.shields.io/badge/Python-3.12-C9A227?style=for-the-badge&logo=python&logoColor=C9A227&labelColor=0B0F0C" alt="Python 3.12"><img src="https://img.shields.io/badge/discord.py-2.7-C9A227?style=for-the-badge&logo=discord&logoColor=C9A227&labelColor=0B0F0C" alt="discord.py 2.7"><img src="https://img.shields.io/badge/Lavalink-v4-C9A227?style=for-the-badge&labelColor=0B0F0C" alt="Lavalink v4"><img src="https://img.shields.io/badge/React-19-C9A227?style=for-the-badge&logo=react&logoColor=C9A227&labelColor=0B0F0C" alt="React 19"><img src="https://img.shields.io/badge/TypeScript-5-C9A227?style=for-the-badge&logo=typescript&logoColor=C9A227&labelColor=0B0F0C" alt="TypeScript 5">
</p>

**[Live station page →](https://trippixn.com/Mazaj)**

</div>

<img src="assets/divider.png" width="100%" alt="">

<div align="center">

Mazaj is a private bot for [discord.gg/syria](https://discord.gg/syria). This is
a preview of what it does and how it's put together — the source, its
configuration and its audio library stay private.

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

<div align="center">

<picture><source media="(prefers-color-scheme: dark)" srcset="assets/mark-dark.png"><img alt="Trippixn" src="assets/mark-light.png" width="30"></picture>

Built by **[Trippixn](https://trippixn.com)** &nbsp;·&nbsp; [discord.gg/syria](https://discord.gg/syria)

<img src="assets/divider.png" width="440" alt="">

<sub>Mazaj is a private bot. This repository is a preview — the source, its configuration and its audio library are not published.</sub>

</div>
