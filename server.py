"""
Musafir — local music player backend ("music for every mile").

Scans the music/ folder for audio files, serves the player UI, and runs a
WebSocket that keeps every listener on the same track at the same position
(a "listen together" room) plus a live online count.

Drop .mp3 / .m4a / .ogg / .wav / .flac / .aac files into music/ and restart.

Run:
    py server.py
Then open http://localhost:8080
"""

import mimetypes
import time
import urllib.parse
import weakref
from pathlib import Path

from aiohttp import web, WSMsgType
import json


def _silence_proactor_connection_reset():
    """Suppress noisy (harmless) WinError 10054 tracebacks on Windows.

    When a client (browser/phone) drops a connection abruptly, the asyncio
    Proactor event loop logs a ConnectionResetError from _call_connection_lost
    even though nothing is actually broken. Wrap it to ignore that one error.
    """
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
    except Exception:
        return

    orig = _ProactorBasePipeTransport._call_connection_lost

    def quiet_call_connection_lost(self, exc):
        try:
            orig(self, exc)
        except (ConnectionResetError, ConnectionAbortedError):
            pass

    _ProactorBasePipeTransport._call_connection_lost = quiet_call_connection_lost


_silence_proactor_connection_reset()

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
except Exception:
    MutagenFile = None
    ID3 = None

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
MUSIC_DIR = BASE_DIR / "music"

AUDIO_EXTS = {".mp3", ".m4a", ".ogg", ".oga", ".wav", ".flac", ".aac", ".opus"}

mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/ogg", ".oga")
mimetypes.add_type("audio/opus", ".opus")
mimetypes.add_type("audio/flac", ".flac")


def prettify(name: str) -> str:
    """Turn a filename stem into a readable title, splitting 'Artist - Title'."""
    stem = name.replace("_", " ").strip()
    return stem


def read_tags(path):
    """Return (title, artist, has_art) from embedded ID3/metadata, best-effort."""
    title = artist = ""
    has_art = False
    if MutagenFile is not None:
        try:
            easy = MutagenFile(path, easy=True)
            if easy and easy.tags:
                title = (easy.tags.get("title", [""])[0] or "").strip()
                artist = (easy.tags.get("artist", [""])[0] or "").strip()
            # Album art lives in the non-easy tags (APIC for mp3).
            raw = MutagenFile(path)
            if raw is not None and raw.tags is not None:
                keys = list(raw.tags.keys())
                has_art = any(k.startswith("APIC") for k in keys) or "covr" in keys
        except Exception:
            pass
    return title, artist, has_art


def scan_tracks():
    """Build the track list from files in music/, preferring embedded tags."""
    if not MUSIC_DIR.exists():
        return []
    tracks = []
    for p in sorted(MUSIC_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            stem = p.stem
            f_artist, f_title = "", prettify(stem)
            if " - " in stem:
                left, right = stem.split(" - ", 1)
                f_artist, f_title = prettify(left), prettify(right)

            t_title, t_artist, has_art = read_tags(p)
            title = t_title or f_title
            artist = t_artist or f_artist

            query = urllib.parse.quote(f"{artist} {title}".strip())
            tracks.append({
                "id": p.name,
                "title": title,
                "artist": artist or "Unknown Artist",
                "src": "/media/" + urllib.parse.quote(p.name),
                "art": ("/art/" + urllib.parse.quote(p.name)) if has_art else "",
                "spotify": f"https://open.spotify.com/search/{query}",
                "ytMusic": f"https://music.youtube.com/search?q={query}",
            })
    return tracks


class Room:
    """Shared library + connected-listener count.

    Playback is independent per user (handled entirely client-side), so the
    server only tracks the available songs and how many people are online.
    """

    def __init__(self):
        self.tracks = scan_tracks()
        self.sockets = weakref.WeakSet()

    def snapshot(self):
        return {
            "type": "state",
            "online": len(self.sockets),
            "tracks": self.tracks,
        }

    async def broadcast(self):
        data = json.dumps(self.snapshot())
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_str(data)
            except ConnectionResetError:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


async def index_handler(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def media_handler(request):
    """Stream an audio file from music/ (supports Range for seeking)."""
    name = urllib.parse.unquote(request.match_info["name"])
    # Prevent path traversal — only allow plain filenames inside music/.
    if "/" in name or "\\" in name or name.startswith("."):
        raise web.HTTPForbidden()
    path = (MUSIC_DIR / name).resolve()
    if not str(path).startswith(str(MUSIC_DIR.resolve())) or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)  # FileResponse handles Range requests


def _safe_music_path(name):
    """Resolve a plain filename inside MUSIC_DIR, or None if unsafe/missing."""
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    path = (MUSIC_DIR / name).resolve()
    if not str(path).startswith(str(MUSIC_DIR.resolve())) or not path.is_file():
        return None
    return path


async def art_handler(request):
    """Extract and serve embedded album art for a track."""
    name = urllib.parse.unquote(request.match_info["name"])
    path = _safe_music_path(name)
    if path is None or MutagenFile is None:
        raise web.HTTPNotFound()
    try:
        raw = MutagenFile(path)
        data, mime = None, "image/jpeg"
        if raw is not None and raw.tags is not None:
            for k in raw.tags.keys():
                if k.startswith("APIC"):
                    apic = raw.tags[k]
                    data, mime = apic.data, (apic.mime or "image/jpeg")
                    break
            if data is None and "covr" in raw.tags:  # mp4/m4a cover
                covr = raw.tags["covr"][0]
                data = bytes(covr)
                mime = "image/png" if covr.imageformat == covr.FORMAT_PNG else "image/jpeg"
        if not data:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type=mime,
                            headers={"Cache-Control": "public, max-age=86400"})
    except web.HTTPException:
        raise
    except Exception:
        raise web.HTTPNotFound()


async def rescan_handler(request):
    room: Room = request.app["room"]
    room.tracks = scan_tracks()
    await room.broadcast()
    return web.json_response({"count": len(room.tracks)})


async def ws_handler(request):
    room: Room = request.app["room"]
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    room.sockets.add(ws)
    # Send the library to this listener, then update everyone's online count.
    await ws.send_str(json.dumps(room.snapshot()))
    await room.broadcast()

    try:
        # Playback is per-user and fully client-side; we only need to keep the
        # socket open (for the online count) and drain any incoming messages.
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        room.sockets.discard(ws)
        await room.broadcast()

    return ws


def make_app():
    app = web.Application()
    app["room"] = Room()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/media/{name}", media_handler)
    app.router.add_get("/art/{name}", art_handler)
    app.router.add_post("/rescan", rescan_handler)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    return app


PORT = 8080


def _free_port(port):
    """On Windows, kill any process already LISTENING on `port`.

    Avoids the common WinError 10048 ("only one usage of each socket address")
    when an old server instance is still holding the port. Best-effort: if the
    lookup or kill fails, we just carry on and let bind() report the problem.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return
    pids = set()
    needle = f":{port} "
    for line in out.splitlines():
        if needle in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, timeout=5)
            print(f"  (freed port {port}: stopped stale process PID {pid})")
        except Exception:
            pass


if __name__ == "__main__":
    _free_port(PORT)
    app = make_app()
    n = len(app["room"].tracks)
    print(f"Musafir running at http://localhost:{PORT}  ({n} track(s) in music/)")
    if n == 0:
        print("  -> music/ is empty. Drop audio files in there and refresh the page.")
    try:
        web.run_app(app, host="0.0.0.0", port=PORT)
    except OSError as e:
        if getattr(e, "errno", None) == 10048 or "10048" in str(e):
            print(f"\nPort {PORT} is still in use. Close whatever is using it and try again,")
            print("or change PORT near the bottom of server.py to a free port (e.g. 8090).")
        else:
            raise
