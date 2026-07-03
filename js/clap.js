// Clap-to-wake. Always-on microphone watcher that fires ONLY on a loud,
// sharp clap — not on talking, music, or a bumped desk.
//
// A clap has a signature no other everyday sound quite has:
//   1. LOUD      — the peak must clear an absolute loudness threshold
//                  (user-tunable; this is the "has to be loud enough" gate).
//   2. SUDDEN    — the room must be comparatively quiet right before it
//                  (speech carries sustained energy, so a loud word mid-
//                  sentence fails this test).
//   3. SHORT     — energy must collapse again within ~200ms (a shout or a
//                  sustained note stays hot and is rejected).
//   4. ABOVE THE FLOOR — the peak must dwarf the rolling noise floor, so a
//                  generally loud room raises the bar instead of tripping it.
//
// Uses a ScriptProcessorNode (deprecated but universal) so buffers keep
// arriving from the audio thread even when the render loop is paused —
// the ears stay open while the orb window is in the background.

const LS_KEY = 'donald.clapThreshold';

export class ClapDetector {
  constructor({ threshold = null, onClap = null, onLevel = null, onState = null } = {}) {
    // Absolute peak amplitude (0..1) a clap must reach. 0.45 ≈ a real,
    // deliberate clap near the machine; normal speech peaks well under it.
    const saved = parseFloat(localStorage.getItem(LS_KEY));
    this.threshold = threshold ?? (Number.isFinite(saved) ? saved : 0.45);

    this.floorRatio = 5;      // peak must be ≥ this × the rolling noise floor
    this.quietBefore = 0.35;  // pre-buffer RMS must be < peak × this…
    this.quietBeforeAbs = 0.12; // …and under this absolute RMS (rejects speech)
    this.decayRatio = 0.25;   // follow-up RMS must fall below peak × this
    this.refractoryMs = 1200; // ignore everything briefly after a wake

    this.onClap = onClap;
    this.onLevel = onLevel;   // (rms, peak) each buffer — for the HUD meter
    this.onState = onState;   // 'off' | 'arming' | 'armed' | 'blocked' | 'paused'

    this.state = 'off';
    this.ctx = null;
    this.stream = null;
    this._node = null;
    this._paused = false;

    // Detection state.
    this._floor = 0.01;       // rolling noise-floor RMS
    this._prevRms = 0;
    this._candidate = null;   // { peak, buffersLeft }
    this._blockedUntil = 0;
  }

  setThreshold(v) {
    this.threshold = Math.min(0.95, Math.max(0.1, v));
    localStorage.setItem(LS_KEY, String(this.threshold));
  }

  // Arm the ears. Needs mic permission; safe to call again after a denial.
  async start() {
    if (this.ctx) return true;
    this._setState('arming');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false, // keep the raw transient — AEC softens claps
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
    } catch (err) {
      this._setState('blocked');
      return false;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx();
    const src = this.ctx.createMediaStreamSource(this.stream);
    // ~85ms buffers at 48kHz: long enough to catch the whole transient,
    // short enough that "the two buffers after" ≈ 170ms of decay window.
    this._node = this.ctx.createScriptProcessor(4096, 1, 1);
    this._node.onaudioprocess = (e) => this._process(e.inputBuffer.getChannelData(0));
    src.connect(this._node);
    // Chrome only runs a ScriptProcessor that is connected onward; a zero-gain
    // sink keeps it running without feeding the mic back to the speakers.
    const sink = this.ctx.createGain();
    sink.gain.value = 0;
    this._node.connect(sink);
    sink.connect(this.ctx.destination);
    if (this.ctx.state === 'suspended') {
      // Will be resumed by the first user gesture (see resume()).
      try { await this.ctx.resume(); } catch { /* gesture needed */ }
    }
    this._setState(this.ctx.state === 'running' ? 'armed' : 'arming');
    return true;
  }

  resume() {
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().then(() => this._setState(this._paused ? 'paused' : 'armed'));
    }
  }

  // Temporarily stop firing (e.g. while Donald is listening or speaking, so
  // his own voice through the speakers can't re-wake him).
  pause() { this._paused = true; this._candidate = null; this._setState(this.ctx ? 'paused' : 'off'); }
  unpause() {
    this._paused = false;
    this._blockedUntil = performance.now() + 400; // don't eat a speaker tail
    this._setState(this.ctx ? (this.ctx.state === 'running' ? 'armed' : 'arming') : 'off');
  }

  _setState(s) {
    if (this.state === s) return;
    this.state = s;
    if (this.onState) this.onState(s);
  }

  _process(samples) {
    let peak = 0, sum = 0;
    for (let i = 0; i < samples.length; i++) {
      const v = samples[i];
      const a = v < 0 ? -v : v;
      if (a > peak) peak = a;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / samples.length);
    if (this.onLevel) this.onLevel(rms, peak);

    const now = performance.now();
    const prevRms = this._prevRms;
    this._prevRms = rms;

    if (this._paused || now < this._blockedUntil) { this._candidate = null; return; }
    if (this.ctx && this.ctx.state !== 'running') return;

    // Confirm phase: a candidate clap must DIE DOWN, not sustain.
    if (this._candidate) {
      const c = this._candidate;
      if (rms > c.peak * this.decayRatio) {
        this._candidate = null; // still loud → shout/music, not a clap
      } else if (--c.buffersLeft <= 0) {
        this._candidate = null;
        this._blockedUntil = now + this.refractoryMs;
        if (this.onClap) this.onClap(c.peak);
      }
      return;
    }

    // Trigger phase: loud enough, sudden, and far above the room's floor.
    const loudEnough = peak >= this.threshold;
    const aboveFloor = peak >= this._floor * this.floorRatio;
    const wasQuiet = prevRms < Math.min(peak * this.quietBefore, this.quietBeforeAbs);
    if (loudEnough && aboveFloor && wasQuiet) {
      this._candidate = { peak, buffersLeft: 2 }; // ~170ms decay check
      return;
    }

    // Only learn the floor from non-candidate buffers (slow EMA, ~2s).
    this._floor = Math.max(0.003, this._floor * 0.95 + rms * 0.05);
  }

  dispose() {
    if (this._node) { try { this._node.disconnect(); } catch {} }
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    if (this.ctx) { try { this.ctx.close(); } catch {} }
    this.ctx = null; this.stream = null; this._node = null;
    this._setState('off');
  }
}
