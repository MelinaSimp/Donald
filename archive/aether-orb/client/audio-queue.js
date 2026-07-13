// Client-side audio queue with sequential playback.
//
// This is the other half of the latency fix ("Bottleneck B"). Instead of
// waiting for one big audio blob, the client receives per-sentence
// `speak_segment` events and plays them in order. While segment N plays,
// segment N+1 can already be downloading. Each segment is one short sentence,
// so it downloads fast and the first audible word arrives quickly.

const logEl = document.getElementById("log");
const orb = document.getElementById("orb");
const player = document.getElementById("player");
const input = document.getElementById("text");

function logLine(s) {
  logEl.textContent += s + "\n";
  logEl.scrollTop = logEl.scrollHeight;
}

// --- queue state -----------------------------------------------------------
let activeBaseTurnId = null;
let audioQueue = [];
let currentlyPlaying = false;
let lastSegmentWasFinal = false;
let currentFetchAbort = null;
let firstAudioPending = false; // for measuring time-to-first-audio

function onSpeakSegment(msg) {
  if (activeBaseTurnId === null && audioQueue.length === 0 && !currentlyPlaying) {
    activeBaseTurnId = msg.base_turn_id;
    firstAudioPending = true;
    orb.classList.add("speaking");
  } else if (msg.base_turn_id !== activeBaseTurnId) {
    // Stale segment from a turn the user already interrupted.
    console.warn("dropping stale segment", msg.base_turn_id);
    return;
  }
  audioQueue.push(msg);
  pumpQueue();
}

function pumpQueue() {
  if (currentlyPlaying || audioQueue.length === 0) return;
  const seg = audioQueue.shift();
  lastSegmentWasFinal = !!seg.is_final;
  currentlyPlaying = true;
  playSegmentAudio(seg.turn_id).catch((err) => {
    if (err && err.name === "AbortError") return; // interrupt path
    console.error("segment playback failed", err);
    onSegmentEnded();
  });
}

async function playSegmentAudio(turnId) {
  currentFetchAbort = new AbortController();
  const url = `/api/tts/${encodeURIComponent(turnId)}`;
  const resp = await fetch(url, { signal: currentFetchAbort.signal });
  if (!resp.ok) throw new Error(`tts ${resp.status}`);
  // One sentence is small — a per-segment fetch is fast. (A production build
  // can stream playback directly; for a reference, a per-segment blob keeps
  // the visualizer/dual-path option open and is plenty fast.)
  const arr = await resp.arrayBuffer();
  const type = resp.headers.get("content-type") || "audio/mpeg";

  if (firstAudioPending) {
    firstAudioPending = false;
    const dt = ((performance.now() - turnStartedAt) / 1000).toFixed(2);
    logLine(`  [first audio ready in ${dt}s after send]`);
  }

  player.onended = onSegmentEnded;
  player.src = URL.createObjectURL(new Blob([arr], { type }));
  await player.play();
}

function onSegmentEnded() {
  currentlyPlaying = false;
  currentFetchAbort = null;
  if (audioQueue.length > 0) {
    pumpQueue();
    return;
  }
  if (lastSegmentWasFinal) {
    activeBaseTurnId = null;
    lastSegmentWasFinal = false;
    orb.classList.remove("speaking");
    logLine("  [turn complete]");
  }
  // else: queue drained but more segments still expected — idle until next msg.
}

function onUserInterrupt() {
  audioQueue.length = 0;
  if (currentFetchAbort) {
    try { currentFetchAbort.abort(); } catch (_) {}
    currentFetchAbort = null;
  }
  currentlyPlaying = false;
  activeBaseTurnId = null;
  lastSegmentWasFinal = false;
  firstAudioPending = false;
  try { player.pause(); player.currentTime = 0; } catch (_) {}
  orb.classList.remove("speaking");
  logLine("  [interrupted]");
}

// --- websocket -------------------------------------------------------------
let turnStartedAt = 0;
const ws = new WebSocket(`ws://${location.host}/ws`);

ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.type === "speak_segment") {
    onSpeakSegment(msg);
  } else if (msg.type === "transcript_delta") {
    logLine("assistant: " + msg.text);
  }
};

function sendMessage() {
  const text = input.value.trim();
  if (!text || ws.readyState !== WebSocket.OPEN) return;
  onUserInterrupt(); // barge-in: cancel any in-flight turn
  turnStartedAt = performance.now();
  logLine("you: " + text);
  ws.send(JSON.stringify({ type: "user_message", text }));
  input.value = "";
}

document.getElementById("send").onclick = sendMessage;
document.getElementById("stop").onclick = onUserInterrupt;
input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

fetch("/api/config")
  .then((r) => r.json())
  .then((c) => {
    document.getElementById("cfg").textContent =
      `model=${c.llm_model} (mock=${c.mock_llm}) · tts=${c.tts_provider} · vad=${c.vad_silence_ms}ms`;
  });
