import { dampAsym, clamp } from './util.js';

// Voice reactivity. Each frame we read two values — overall LOUDNESS and BASS —
// and feed them to the orb's surface displacement and size pulse.
//
// Auto-selection: if a real analyser is attached AND signal is actually
// flowing, use it; otherwise fall back to a synthetic motion that mimics the
// cadence of speech, so the orb always looks alive.
//
// The values are smoothed ASYMMETRICALLY — they jump up fast on a loud
// syllable and ease back down slowly — so the orb leaps to life rather than
// twitching frame to frame.
//
// ── iOS pitfall (read before shipping real audio on mobile) ──────────────
// iOS Safari is fussy about feeding audio into an analyser while also playing
// it aloud. The robust pattern:
//   • Create the AudioContext from inside a real user tap (resume() on touch).
//   • Play the audible audio normally, and feed a SILENT DUPLICATE of the same
//     audio into a separate analyser graph just to read its levels.
//   • Use a SEPARATE AudioContext for the microphone.
// attachElement() below supports the silent-duplicate pattern via {silent}.

export class AudioReactor {
  constructor() {
    this.level = 0;     // smoothed loudness 0..1
    this.bass = 0;      // smoothed bass 0..1
    this.analyser = null;
    this.freq = null;
    this.ctx = null;
    this.hasRealSignal = false;
    this._silenceTime = 0;
  }

  // Attach a WebAudio analyser from an AudioContext + source node.
  _attach(ctx, sourceNode) {
    this.ctx = ctx;
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.6;
    this.freq = new Uint8Array(this.analyser.frequencyBinCount);
    sourceNode.connect(this.analyser);
    return this.analyser;
  }

  // Microphone. Uses its OWN context (per the iOS guidance above).
  async attachMic() {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const src = ctx.createMediaStreamSource(stream);
    this._attach(ctx, src); // mic analyser is not connected to destination
    return ctx;
  }

  // Spoken-response audio element. {silent:true} reads levels without routing
  // to the speakers (pair it with a second, audible <audio> for playback).
  attachElement(audioEl, { silent = false } = {}) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaElementSource(audioEl);
    const analyser = this._attach(ctx, src);
    if (!silent) analyser.connect(ctx.destination);
    return ctx;
  }

  resume() { if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }

  // Read the real analyser. Returns {level, bass} or null if no/quiet signal.
  _readReal() {
    if (!this.analyser) return null;
    this.analyser.getByteFrequencyData(this.freq);
    const n = this.freq.length;
    let sum = 0, bassSum = 0;
    const bassBins = Math.max(1, Math.floor(n * 0.08));
    for (let i = 0; i < n; i++) {
      const v = this.freq[i] / 255;
      sum += v * v;
      if (i < bassBins) bassSum += v;
    }
    const level = Math.sqrt(sum / n);
    const bass = bassSum / bassBins;
    return { level: clamp(level * 2.4, 0, 1), bass: clamp(bass * 1.4, 0, 1) };
  }

  // Synthetic motion shaped to the active state's character.
  _synthetic(t, state) {
    if (state === 'speaking') {
      // Layered incommensurate sines + a slow envelope ≈ speech cadence.
      const env = 0.5 + 0.5 * Math.sin(t * 1.7);
      const syll = Math.abs(Math.sin(t * 6.3) * Math.sin(t * 3.1 + 1.0));
      const fast = 0.5 + 0.5 * Math.sin(t * 11.0);
      const lvl = clamp((0.25 + 0.6 * syll) * (0.5 + 0.5 * env) * (0.7 + 0.3 * fast), 0, 1);
      const bass = clamp(0.2 + 0.5 * Math.abs(Math.sin(t * 2.2)), 0, 1);
      return { level: lvl, bass };
    }
    if (state === 'listening') {
      // Gentle wavering — "I'm hearing you" without faking words.
      const lvl = 0.06 + 0.10 * (0.5 + 0.5 * Math.sin(t * 1.3 + Math.sin(t * 0.7)));
      return { level: lvl, bass: lvl * 0.6 };
    }
    if (state === 'processing') {
      const lvl = 0.04 + 0.05 * (0.5 + 0.5 * Math.sin(t * 2.5));
      return { level: lvl, bass: lvl };
    }
    return { level: 0, bass: 0 }; // idle / error: near-still
  }

  // Called each frame. Auto-selects real vs synthetic, applies asymmetric easing.
  sample(dt, t, state) {
    const real = this._readReal();
    let target;
    if (real && real.level > 0.04) {
      this.hasRealSignal = true;
      this._silenceTime = 0;
      target = real;
    } else {
      // Real signal absent/quiet → synthetic so the orb stays alive.
      this._silenceTime += dt;
      target = this._synthetic(t, state);
    }

    // Jump up fast (lambda 18), fall away slowly (lambda 3).
    this.level = dampAsym(this.level, target.level, 18, 3, dt);
    this.bass = dampAsym(this.bass, target.bass, 16, 3, dt);
    return { level: this.level, bass: this.bass };
  }
}
