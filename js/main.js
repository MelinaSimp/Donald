import * as THREE from 'three';
import { Orb } from './orb.js';
import { Background } from './background.js';
import { AudioReactor } from './audio.js';
import { Constellation } from './constellation.js';
import { AGENTS } from './agents.js';
import { buildStates } from './states.js';
import { prefersReducedMotion } from './util.js';

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
    this.reducedMotion = prefersReducedMotion();

    this.background = new Background(this.root); // furthest-back layer
    this._initOrbLayer();
    this.audio = new AudioReactor();

    // Tier 4 — the floating sub-agent constellation.
    this.labelRoot = document.getElementById('labels');
    this.constellation = new Constellation(this.scene, this.camera, this.labelRoot);
    this.constellation.setReducedMotion(this.reducedMotion);
    for (const a of AGENTS) this.constellation.add(a);

    // A live, eased copy of the current mood so cross-fades between states are
    // smooth even if the target flips mid-transition.
    this.mood = this._cloneMood(this.states.idle);

    this._onResize = this._resize.bind(this);
    addEventListener('resize', this._onResize);
    this._resize();

    this._tick = this._tick.bind(this);
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

  _resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.background.resize();
  }

  _tick() {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.elapsedTime;

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

    // Constellation orbits + label tracking.
    this.constellation.update(dt, t, { width: innerWidth, height: innerHeight });

    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    removeEventListener('resize', this._onResize);
    this.renderer.setAnimationLoop(null);
    this.orb.dispose();
    this.renderer.dispose();
  }
}

// Boot + expose for console testing.
const root = document.getElementById('scene');
const app = new CosmicInterface(root);
window.cosmic = app;
window.setState = (n) => app.setState(n);
// Real audio must be unlocked by a user gesture (and resumed for iOS).
window.enableMic = () => app.audio.attachMic().then(() => app.audio.resume());
window.attachAudio = (el, opts) => app.audio.attachElement(el, opts);
addEventListener('pointerdown', () => app.audio.resume(), { passive: true });
