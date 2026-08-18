// Musafir — INDEPENDENT local audio player ("music for every mile").
// Each user controls their own playback (any track, play/pause, seek) with no
// effect on anyone else. The WebSocket is used only for the shared track list
// and the live "online" count — not for playback state.

const $ = (id) => document.getElementById(id);
const audio = $("audio");

let ws = null;
let tracks = [];        // shared library from the server
let myIndex = 0;        // THIS user's current track
let seeking = false;    // user dragging the seek bar

// ---- WebSocket: track list + online count only ----
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type !== "state") return;
    $("onlineCount").textContent = msg.online;

    const hadTracks = tracks.length > 0;
    tracks = msg.tracks || [];
    if (tracks.length === 0) {
      $("hint").textContent = "No music found. Drop audio files into the music/ folder and restart the server.";
      return;
    }
    // First time we receive the library: show the first track (but don't autoplay).
    if (!hadTracks) {
      if (myIndex >= tracks.length) myIndex = 0;
      renderMeta();
      updatePlayBtn();
    }
  };
  ws.onclose = () => setTimeout(connect, 1500);
}

// ---- Playback (all local) ----
function loadTrack(index, autoplay) {
  const t = tracks[index];
  if (!t) return;
  myIndex = index;
  audio.src = t.src;
  audio.load();
  renderMeta();
  if (autoplay) {
    audio.play().catch(() => {
      $("hint").textContent = "Tap ▶ to start playback.";
    });
  }
  updatePlayBtn();
}

function togglePlay() {
  if (tracks.length === 0) return;
  // Nothing loaded yet? Load the current track and play it.
  if (!audio.src) { loadTrack(myIndex, true); return; }
  if (audio.paused) {
    audio.play().catch(() => { $("hint").textContent = "Tap ▶ to start playback."; });
  } else {
    audio.pause();
  }
}

function nextTrack() {
  if (tracks.length === 0) return;
  loadTrack((myIndex + 1) % tracks.length, true);
}

function prevTrack() {
  if (tracks.length === 0) return;
  loadTrack((myIndex - 1 + tracks.length) % tracks.length, true);
}

// ---- UI ----
function renderMeta() {
  const t = tracks[myIndex];
  if (!t) { $("trackTitle").textContent = "No tracks"; $("trackArtist").textContent = ""; return; }
  $("trackTitle").textContent = t.title;
  $("trackArtist").textContent = t.artist;
  $("spotifyLink").href = t.spotify || "#";
  $("ytmusicLink").href = t.ytMusic || "#";
  setArtwork(t.art || "");
}

// Show album art in the cover + as a blurred full-screen wallpaper.
function setArtwork(url) {
  const coverArt = $("coverArt");
  const wall = $("wallpaper");
  if (url) {
    coverArt.style.backgroundImage = `url("${url}")`;
    coverArt.classList.add("has-art");
    coverArt.textContent = "";
    if (wall) wall.style.backgroundImage = `url("${url}")`;
  } else {
    coverArt.style.backgroundImage = "";
    coverArt.classList.remove("has-art");
    coverArt.textContent = "🎵";
    if (wall) wall.style.backgroundImage = "";
  }
}

function updatePlayBtn() {
  const playing = !!audio.src && !audio.paused;
  $("playBtn").textContent = playing ? "⏸" : "▶";
  $("coverArt").classList.toggle("playing", playing);
}

function fmt(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---- Controls ----
$("playBtn").onclick = togglePlay;
$("nextBtn").onclick = nextTrack;
$("prevBtn").onclick = prevTrack;

$("seekBar").addEventListener("input", () => { seeking = true; });
$("seekBar").addEventListener("change", () => {
  const dur = audio.duration || 0;
  audio.currentTime = (parseFloat($("seekBar").value) / 100) * dur;
  seeking = false;
});

audio.volume = 0.8;

// Keep the play button/cover state in sync with the actual element.
audio.addEventListener("play", updatePlayBtn);
audio.addEventListener("pause", updatePlayBtn);

// Auto-advance to the next track for THIS user only.
audio.addEventListener("ended", nextTrack);

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && e.target.tagName !== "INPUT") {
    e.preventDefault();
    togglePlay();
  }
});

// ---- progress display ----
setInterval(() => {
  if (!seeking) {
    const cur = audio.currentTime || 0;
    const dur = audio.duration || 0;
    $("curTime").textContent = fmt(cur);
    $("durTime").textContent = fmt(dur);
    $("seekBar").value = dur ? (cur / dur) * 100 : 0;
  }
}, 500);

connect();
