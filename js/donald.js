// DonaldController — the always-on desk-side loop, wired to the real gateway.
//
//   CLAP (loud!) ──▶ chime + LISTENING ──▶ speech-to-text ──▶ gateway /ws
//        ▲                                                        │
//        │            events stream back: delta / tool_call /     ▼
//   idle orb ◀── SPEAKING (voice mp3) ◀── hermes_line / tool_result / final
//
// Everything that happens is also written to the OPS TERMINAL, so the orb
// stays the show while the terminal is the record.
//
// If the gateway isn't reachable (opened as a bare static file), the scene
// falls back to the old demo driver so it still looks alive.

import { ClapDetector } from './clap.js';
import { Terminal } from './terminal.js';
import { Transport } from './transport.js';

export class DonaldController {
  constructor(app) {
    this.app = app;
    this.sessionId = 'orb-' + Math.random().toString(36).slice(2, 10);
    this.online = false;
    this.busy = false;        // a turn is in flight
    this.listening = false;   // speech capture in progress
    this._speaking = 0;       // audio clips currently playing
    this._finalSeen = true;
    this._spokeThisTurn = false;
    this._ws = null;
    this._wsBackoff = 1000;

    this.terminal = new Terminal({ onSubmit: (t) => this.send(t) });
    this.clap = new ClapDetector({
      onClap: (peak) => this._onClap(peak),
      onLevel: (rms, peak) => this._onLevel(rms, peak),
      onState: (s) => this._onEarsState(s),
    });

    // Reusable audio element for Donald's voice; the orb reacts to it.
    this._audioEl = new Audio();
    this._audioAttached = false;
    this._audioEl.addEventListener('ended', () => this._voiceEnded());
    this._audioEl.addEventListener('error', () => this._voiceEnded());

    this._bindHud();
  }

  async init() {
    this.terminal.line('sys', 'Donald ops terminal online. ` or T toggles this page; Esc returns to the orb.');
    await this._probeGateway();
    if (this.online) {
      this._connectWs();
    } else {
      this.terminal.line('error', 'gateway unreachable — running the demo loop. Start it with desktop/donald.sh (or python -m gateway.server).');
      this.app.transport = new Transport(this.app, {}); // scripted demo
    }
    // Arm the ears. If the browser wants a gesture first, the first click
    // anywhere (or the EARS chip) finishes the job.
    const ok = await this.clap.start();
    if (!ok) {
      this.terminal.line('error', 'microphone blocked — allow mic access for this site, then click the EARS chip.');
    }
    addEventListener('pointerdown', () => this.clap.resume(), { passive: true });

    addEventListener('keydown', (e) => {
      if (e.target === this.terminal.input) {
        if (e.key === 'Escape') this.terminal.hide();
        return;
      }
      if (e.key === '`' || e.key === 't' || e.key === 'T') {
        e.preventDefault(); // don't type the toggle key into the freshly-focused prompt
        this.terminal.toggle();
      }
      if (e.key === 'Escape' && this.terminal.visible) this.terminal.hide();
    });
  }

  // -- gateway link ---------------------------------------------------------
  async _probeGateway() {
    try {
      const r = await fetch('/health');
      const h = await r.json();
      this.online = true;
      this.terminal.setChip('gateway', `${h.donald_provider}/${h.donald_model}`, 'ok');
      this.terminal.setChip('hermes', h.hermes_reachable ? `up (${h.hermes_mode})` : 'unreachable', h.hermes_reachable ? 'ok' : 'bad');
      this.terminal.line('sys', `gateway ok — brain=${h.donald_model} hermes=${h.hermes_mode}:${h.hermes_target} reachable=${h.hermes_reachable} voice=${h.voice_configured}`);
      if (!h.hermes_reachable) {
        this.terminal.line('error', 'Hermes is not reachable — Donald can talk but not touch the machine. Check HERMES_MODE / container in gateway/.env.');
      }
      this.voiceConfigured = !!h.voice_configured;
    } catch {
      this.online = false;
      this.terminal.setChip('gateway', 'offline', 'bad');
      this.terminal.setChip('hermes', 'unknown', 'warn');
    }
  }

  _connectWs() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this._ws = ws;
    ws.onopen = () => { this._wsBackoff = 1000; };
    ws.onmessage = (e) => {
      try { this.handle(JSON.parse(e.data)); } catch { /* ignore bad frames */ }
    };
    ws.onclose = () => {
      this._ws = null;
      if (this.busy) { this.busy = false; this.app.setState('idle'); }
      this.terminal.setChip('gateway', 'reconnecting…', 'warn');
      setTimeout(() => this._connectWs(), this._wsBackoff);
      this._wsBackoff = Math.min(this._wsBackoff * 2, 15000);
    };
    ws.onerror = () => { try { ws.close(); } catch {} };
  }

  // -- outbound -------------------------------------------------------------
  send(text) {
    text = (text || '').trim();
    if (!text) return false;
    this.terminal.line('you', text);
    if (!this.online || !this._ws || this._ws.readyState !== WebSocket.OPEN) {
      this.terminal.line('error', 'gateway offline — start it and reload.');
      return false;
    }
    if (this.busy) {
      this.terminal.line('sys', 'still working the last one — queued nothing, say it again in a sec.');
      return false;
    }
    this.busy = true;
    this._finalSeen = false;
    this._spokeThisTurn = false;
    this.app.setState('processing');
    this._ws.send(JSON.stringify({ type: 'chat', session_id: this.sessionId, message: text }));
    return true;
  }

  // -- inbound gateway events ----------------------------------------------
  handle(ev) {
    if (!ev || !ev.type) return;
    switch (ev.type) {
      case 'delta':
        this.terminal.line('donald', ev.text);
        break;
      case 'tool_call':
        this.terminal.line('tool', `→ hermes: ${ev.task}${ev.reason ? `  (${ev.reason})` : ''}`);
        this.app.setState('processing');
        this.app.dispatch('hermes');
        this.app.setWorking('hermes', true);
        break;
      case 'hermes_line':
        this.terminal.line('hermes', ev.text);
        break;
      case 'tool_result':
        this.app.setWorking('hermes', false);
        if (ev.declined) this.terminal.line('result', '⨯ declined by user');
        else if (ev.error) this.terminal.line('error', `hermes error: ${ev.error}`);
        else {
          if (ev.flagged) this.terminal.line('error', `⚠ injection-flagged output (${(ev.flag_reasons || []).join(', ')}) — treated as data only`);
          this.terminal.line('result', ev.preview || '(done)');
        }
        break;
      case 'voice':
        this._playVoice(ev);
        break;
      case 'voice_error':
        this.terminal.line('error', `voice: ${ev.error}`);
        break;
      case 'final':
        this.busy = false;
        this._finalSeen = true;
        this.app.setWorking('hermes', false);
        // No ElevenLabs? Fall back to the browser's own voice so Donald
        // still talks back — the agentic feel survives a missing API key.
        if (!this._spokeThisTurn && ev.text) this._speakFallback(ev.text);
        if (this._speaking === 0) this._settle();
        break;
      case 'error':
        this.busy = false;
        this._finalSeen = true;
        this.terminal.line('error', ev.text || 'unknown gateway error');
        this.app.setState('error');
        this.clap.unpause();
        setTimeout(() => { if (!this.busy) this.app.setState('idle'); }, 1600);
        break;
      default:
        break;
    }
  }

  // -- voice out ------------------------------------------------------------
  _playVoice(ev) {
    this._spokeThisTurn = true;
    this._speaking++;
    this.clap.pause(); // don't let Donald's own voice wake Donald
    this.app.setState('speaking');
    if (!this._audioAttached) {
      // Route through the AudioReactor so the orb surface rides the voice.
      try { this.app.audio.attachElement(this._audioEl); this._audioAttached = true; } catch {}
    }
    this._audioEl.src = `data:${ev.mime || 'audio/mpeg'};base64,${ev.audio_b64}`;
    this._audioEl.play().catch(() => this._voiceEnded());
  }

  _speakFallback(text) {
    if (!('speechSynthesis' in window)) return;
    this._spokeThisTurn = true;
    this._speaking++;
    this.clap.pause();
    this.app.setState('speaking');
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02; u.pitch = 0.75; // ballpark gravitas
    u.onend = () => this._voiceEnded();
    u.onerror = () => this._voiceEnded();
    speechSynthesis.speak(u);
  }

  _voiceEnded() {
    this._speaking = Math.max(0, this._speaking - 1);
    if (this._speaking === 0 && this._finalSeen) this._settle();
  }

  _settle() {
    this.app.setState('idle');
    this.clap.unpause();
  }

  // -- clap → listen → transcript --------------------------------------------
  _onClap(peak) {
    if (this.listening) return;
    if (this.busy) {
      this.terminal.line('wake', `clap heard (peak ${peak.toFixed(2)}) — busy, ignoring`);
      return;
    }
    this.terminal.line('wake', `👏 clap detected (peak ${peak.toFixed(2)}) — listening`);
    this._chime();
    this._listen();
  }

  _listen() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      this.terminal.line('error', 'this browser has no speech recognition — use Chrome, or type in the terminal.');
      this.terminal.show();
      return;
    }
    this.listening = true;
    this.clap.pause();
    this.app.setState('listening');
    this._caption('');

    const rec = new SR();
    rec.lang = navigator.language || 'en-US';
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = '';
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      this.listening = false;
      this._caption(null);
      clearTimeout(guard);
      if (finalText.trim()) {
        // clap stays paused while the turn runs; _settle() re-arms it —
        // unless the send failed, in which case settle right away.
        if (!this.send(finalText.trim())) this._settle();
      } else {
        this.terminal.line('sys', 'heard nothing — going back to sleep.');
        this._settle();
      }
    };
    const guard = setTimeout(() => { try { rec.stop(); } catch {} finish(); }, 12000);

    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      this._caption((finalText + interim).trim());
    };
    rec.onerror = (e) => {
      if (e.error && e.error !== 'no-speech' && e.error !== 'aborted') {
        this.terminal.line('error', `speech recognition: ${e.error}`);
      }
      finish();
    };
    rec.onend = finish;
    try { rec.start(); } catch { finish(); }
  }

  _chime() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = this._chimeCtx || (this._chimeCtx = new Ctx());
      if (ctx.state === 'suspended') ctx.resume();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.setValueAtTime(880, ctx.currentTime);
      o.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.12);
      g.gain.setValueAtTime(0.15, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
      o.connect(g); g.connect(ctx.destination);
      o.start(); o.stop(ctx.currentTime + 0.4);
    } catch { /* purely cosmetic */ }
  }

  // -- HUD ------------------------------------------------------------------
  _bindHud() {
    this._earsChip = document.getElementById('ears-chip');
    this._earsMeter = document.getElementById('ears-meter');
    this._captionEl = document.getElementById('caption');
    const termBtn = document.getElementById('term-toggle');
    if (termBtn) termBtn.addEventListener('click', () => this.terminal.toggle());
    if (this._earsChip) {
      this._earsChip.addEventListener('click', async () => {
        if (this.clap.state === 'blocked' || this.clap.state === 'off') {
          this.clap.dispose();
          await this.clap.start();
        }
        this.clap.resume();
      });
    }
    const slider = document.getElementById('clap-threshold');
    if (slider) {
      slider.value = String(Math.round(this.clap.threshold * 100));
      slider.addEventListener('input', () => {
        this.clap.setThreshold(Number(slider.value) / 100);
      });
      slider.addEventListener('change', () => {
        this.terminal.line('sys', `clap loudness gate set to ${(this.clap.threshold * 100).toFixed(0)}% — quieter sounds will not wake Donald.`);
      });
    }
  }

  _onEarsState(s) {
    const label = { off: 'off', arming: 'click to arm', armed: 'armed', blocked: 'mic blocked', paused: 'paused' }[s] || s;
    if (this._earsChip) {
      this._earsChip.textContent = `👂 ears: ${label}`;
      this._earsChip.classList.toggle('on', s === 'armed');
      this._earsChip.classList.toggle('bad', s === 'blocked');
    }
    const tone = s === 'armed' ? 'ok' : s === 'blocked' ? 'bad' : 'warn';
    this.terminal.setChip('ears', label, tone);
  }

  _onLevel(rms, peak) {
    if (!this._earsMeter) return;
    const pct = Math.min(100, Math.round(peak * 100));
    this._earsMeter.style.width = `${pct}%`;
    this._earsMeter.classList.toggle('hot', peak >= this.clap.threshold);
  }

  _caption(text) {
    if (!this._captionEl) return;
    if (text === null || text === undefined) {
      this._captionEl.classList.remove('show');
      return;
    }
    this._captionEl.textContent = text || '· · ·';
    this._captionEl.classList.add('show');
  }
}
