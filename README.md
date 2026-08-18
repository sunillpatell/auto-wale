# Musafir 🛺 — music for every mile

A lightweight, mobile-first **local music player** aimed at auto/rickshaw
drivers. It plays **your own local audio files** with album art and a blurred
full-screen wallpaper. Each listener has their **own independent player** — play
any song, pause, and seek without affecting anyone else — while a live **online
count** shows how many people are connected.

## Requirements

- Python 3.11+
- `aiohttp` — `py -m pip install aiohttp`

## How to use

1. **Copy your music** into the **`music/`** folder next to `server.py`.
   Supported: `.mp3 .m4a .ogg .wav .flac .aac .opus`

   Tip: name files **`Artist - Title.ext`** and the player splits them into
   artist + title automatically. (Otherwise the filename becomes the title.)

2. **Start the server:**
   ```bash
   py server.py
   ```

3. Open **http://localhost:8080**. Open it in two windows/devices to see the
   sync — press play in one, the other follows.

Added files while it's running? Click **⟳ Rescan** in the Queue panel (no
restart needed).

## How it works

- **`server.py`** scans `music/`, serves the UI, streams audio at `/media/<file>`
  (with HTTP Range support so seeking works), and runs a WebSocket at `/ws`
  holding the authoritative shared state (current track, playing/paused,
  position). Any action (play/pause/seek/next/prev/select) updates the room and
  is broadcast to everyone. The online count = number of live sockets.
- **`static/app.js`** reconciles the local `<audio>` element to the server: if
  it drifts more than 1s from the server's position, it re-seeks.

## Notes

- **First click:** browsers block autoplay until you interact with the page. If
  audio doesn't start, click ▶ once — after that, sync is automatic.
- **Files never leave your machine.** This is a local server; only devices on
  your network that can reach your IP:8080 can connect.

## Layout

```
server.py          Backend: scan + stream + WebSocket sync
music/             ← put your audio files here
static/index.html  Player UI
static/style.css   Dark, mobile-first theme
static/app.js      Audio engine + sync client
```

## Ideas to extend

- Multiple named rooms (`/ws?room=chill`)
- Chat sidebar
- Real album-art extraction from file tags
- Upload tracks from the browser
