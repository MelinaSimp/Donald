import * as THREE from 'three';
import { Orb } from './orb.js';
import { Background } from './background.js';
import { AudioReactor } from './audio.js';
import { Constellation } from './constellation.js';
import { RingSystem } from './rings.js';
import { Effects } from './effects.js';
import { AGENTS } from './agents.js';
import { buildStates } from './states.js';
import { DonaldController } from './donald.js';
import { prefersReducedMotion } from './util.js';

const _wv = new THREE.Vector3();

// ---------------------------------------------------------------------------
// Orchestrator. Builds the layers and runs the single animation loop that
// drives everything. Tiers are added here one at a time; Tier 1 is the orb.
// ---------------------------------------------------------------------------

const ACCENT = '#ff8a3d'; // orange active accent (from the interview)

export class CosmicInterface {
  constructor(root) {
    this.root = root;
    this.states = buildStates(ACCENT);
    this.state = 'idle';
    this.clock = new THREE.Clock();
    this.time = 0;          // manual accumulator → pause/resume can't jump phase
    this.paused = false;
    this.perfMode = false;
    this.reducedMotion = prefersReducedMotion();

    this.background = new Background(this.root); // furthest-back layer
    this.background.reducedMotion = this.reducedMotion;
    this._initOrbLayer();
    this.audio = new AudioReactor();

    // Tier 4 — the floating sub-agent constellation.
    this.labelRoot = document.getElementById('labels');
    this.constellation = new Constellation(this.scene, this.camera, this.labelRoot);
    this.constellation.setReducedMotion(this.reducedMotion);
    for (const a of AGENTS) this.constellation.add(a);

    // Tier 5 — reactions.
    this.rings = new RingSystem(this.scene);
    this.effects = new Effects(this.scene);
    this._pulseTimer = 0;

    // A live, eased copy of the current mood so cross-fades between states are
    // smooth even if the target flips mid-transition.
    this.mood = this._cloneMood(this.states.idle);

    this._onResize = this._resize.bind(this);
    addEventListener('resize', this._onResize);
    this._resize();

    // Battery/focus: pause when the tab is hidden, resume cleanly.
    this._onVisibility = () => (document.hidden ? this.pause() : this.resume());
    document.addEventListener('visibilitychange', this._onVisibility);

    // Gracefully survive a lost WebGL context (matters on iOS).
    this.renderer.domElement.addEventListener('webglcontextlost', (e) => {
      e.preventDefault(); this.pause();
    });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => this.resume());

    this._initControls();

    this._tick = this._tick.bind(this);
    this.renderer.setAnimationLoop(this._tick);
  }

  _initControls() {
    // Keyboard: P = performance mode. Plus a small on-screen toggle.
    addEventListener('keydown', (e) => {
      if (e.key === 'p' || e.key === 'P') this.setPerformanceMode(!this.perfMode);
    });
    const btn = document.getElementById('perf-toggle');
    if (btn) btn.addEventListener('click', () => this.setPerformanceMode(!this.perfMode));
    this._perfBtn = btn;
  }

  setPerformanceMode(on) {
    this.perfMode = on;
    this.background.setPerformanceMode(on);
    if (this._perfBtn) this._perfBtn.classList.toggle('on', on);
  }

  // Pause/resume the whole loop. Used for tab-hide and full-screen panels.
  pause() {
    if (this.paused) return;
    this.paused = true;
    this.renderer.setAnimationLoop(null);
  }

  resume() {
    if (!this.paused) return;
    this.paused = false;
    this.clock.getDelta(); // discard the gap so dt stays small on the first frame
    this.renderer.setAnimationLoop(this._tick);
  }

  _initOrbLayer() {
    const canvas = document.createElement('canvas');
    canvas.className = 'layer orb-layer';
    this.root.appendChild(canvas);

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true, // transparent so it composites over the background layer
      powerPreference: 'high-performance',
    });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
    this.camera.position.set(0, 0, 4.8); // centered, with breathing room around

    this.orb = new Orb();
    this.scene.add(this.orb.group);
  }

  _cloneMood(m) {
    return {
      color: m.color.clone(),
      rimColor: m.rimColor.clone(),
      displace: m.displace, churn: m.churn, brightness: m.brightness,
      rimPower: m.rimPower, halo: m.halo, spin: m.spin,
      spinExtra: m.spinExtra, size: m.size, pulse: m.pulse,
      bgGlow: m.bgGlow, rings: m.rings,
    };
  }

  setState(name) {
    if (!this.states[name]) return;
    this.state = name;
  }

  // --- Tier 5 public reaction API (also exposed on window) ---

  // Fire a dispatch beam + flare + sonar ping at an agent.
  dispatch(agentId) {
    const node = this.constellation.get(agentId);
    if (node) this.effects.dispatch(node);
  }

  // Mark an agent working: steady pulse, and dock near its panel if one exists
  // (an element with [data-agent="<id>"]); otherwise it just pulses in orbit.
  setWorking(agentId, on) {
    this.constellation.setWorking(agentId, on);
    const panel = document.querySelector(`[data-agent="${CSS.escape(agentId)}"]`);
    if (on && panel) {
      this.constellation.dock(agentId, () => this._panelToWorld(panel));
    } else if (!on) {
      this.constellation.undock(agentId);
    }
  }

  // Add a brand-new agent at runtime (avatar + label generated on the fly).
  addAgent(def) { return this.constellation.add(def); }

  // Project a panel's on-screen center to a world point on the orb's z-plane.
  _panelToWorld(panel) {
    const r = panel.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    const ndcX = ((r.left + r.width / 2) / innerWidth) * 2 - 1;
    const ndcY = -(((r.top + r.height / 2) / innerHeight) * 2 - 1);
    _wv.set(ndcX, ndcY, 0.5).unproject(this.camera);
    _wv.sub(this.camera.position).normalize();
    const tdist = (0 - this.camera.position.z) / _wv.z;
    return _wv.multiplyScalar(tdist).add(this.camera.position);
  }

  _resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.background.resize();
  }

  _tick() {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    this.time += dt;       // never jumps, even after a long pause
    const t = this.time;

    const target = this.states[this.state];

    // Processing cycles its hue; resolve a per-frame target color for it.
    if (target.cycle) {
      const k = 0.5 + 0.5 * Math.sin(t * target.cycle.speed * Math.PI * 2);
      target.color.copy(target.cycle.a).lerp(target.cycle.b, k);
    }

    const audio = this.audio.sample(dt, t, this.state);
    this.orb.update(dt, t, target, audio);

    // Background reads the orb's live color so its glow tracks the orb.
    this.background.update(dt, t, target.bgGlow, this.orb.uniforms.uColor.value);

    // Processing rings (the helix) fade in/out with the processing state.
    this.rings.update(dt, t, target.rings);

    // Faint pulse waves ripple from the orb periodically while it's thinking.
    if (target.rings) {
      this._pulseTimer -= dt;
      if (this._pulseTimer <= 0) {
        this._pulseTimer = 2.6;
        this.effects.pulse(this.orb.uniforms.uColor.value.clone());
      }
    }

    // Transient effects (beams, pings), then the constellation + labels.
    this.effects.update(dt);
    this.constellation.update(dt, t, { width: innerWidth, height: innerHeight });

    this.renderer.render(this.scene, this.camera);

    // Drive the demo/transport on the same clock.
    if (this.transport) this.transport.update(dt);
  }

  dispose() {
    removeEventListener('resize', this._onResize);
    document.removeEventListener('visibilitychange', this._onVisibility);
    this.renderer.setAnimationLoop(null);
    if (this.transport) this.transport.dispose();
    this.constellation.dispose();
    this.rings.dispose();
    this.effects.dispose();
    this.orb.dispose();
    this.background.dispose();
    this.renderer.dispose();
  }
}

// Boot + expose for console testing.
const root = document.getElementById('scene');
const app = new CosmicInterface(root);
window.cosmic = app;
window.setState = (n) => app.setState(n);
window.dispatch = (id) => app.dispatch(id);
window.setWorking = (id, on) => app.setWorking(id, on);
window.addAgent = (def) => app.addAgent(def);
window.setPerformanceMode = (on) => app.setPerformanceMode(on);
// Real audio must be unlocked by a user gesture (and resumed for iOS).
window.enableMic = () => app.audio.attachMic().then(() => app.audio.resume());
window.attachAudio = (el, opts) => app.audio.attachElement(el, opts);
addEventListener('pointerdown', () => app.audio.resume(), { passive: true });

// --- Donald ------------------------------------------------------------------
// The always-on desk-side loop: clap-to-wake, speech in, gateway /ws events
// out to the orb + the ops terminal. Falls back to the scripted demo driver
// when the gateway isn't reachable (e.g. opened as a bare static file).
const donald = new DonaldController(app);
donald.init();
window.donald = donald;
window.donaldEvent = (msg) => donald.handle(msg); // route a gateway event by hand
