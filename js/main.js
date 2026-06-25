import * as THREE from 'three';
import { Orb } from './orb.js';
import { Background } from './background.js';
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

    this.orb.update(dt, t, target, null /* audio added in Tier 3 */);

    // Background reads the orb's live color so its glow tracks the orb.
    this.background.update(dt, t, target.bgGlow, this.orb.uniforms.uColor.value);

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
