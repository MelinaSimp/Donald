import * as THREE from 'three';
import { smoothstep } from './util.js';

// Transient reactions that live in the orb scene:
//   • Dispatch beam — a thick glowing line from the orb out to an agent, with
//     a pulse that races out and back; the agent flares (peaks mid-flight).
//   • Sonar ping — an expanding ring that scales out and fades (at the orb on
//     send, at the agent at the beam's peak).
//   • Pulse wave — faint rings rippling out from the orb while it's thinking.

const ORIGIN = new THREE.Vector3(0, 0, 0);
const _dir = new THREE.Vector3();
const _mid = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);
const _q = new THREE.Quaternion();

// Soft ring texture: transparent center, bright thin ring, used for pings.
function makeRingTexture() {
  const S = 128;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, S * 0.30, S / 2, S / 2, S * 0.5);
  g.addColorStop(0.0, 'rgba(255,255,255,0)');
  g.addColorStop(0.72, 'rgba(255,255,255,0.9)');
  g.addColorStop(0.85, 'rgba(255,255,255,1)');
  g.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export class Effects {
  constructor(scene) {
    this.scene = scene;
    this.ringTex = makeRingTexture();
    this.beams = [];
    this.pings = [];
  }

  // Fire a dispatch beam from the orb out to a constellation node.
  dispatch(node) {
    const color = node.color.clone();
    // Thick glowing beam (a thin cylinder we orient + stretch each frame).
    const geo = new THREE.CylinderGeometry(0.045, 0.045, 1, 8, 1, true);
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      uniforms: { uColor: { value: color }, uBand: { value: 0 }, uEnv: { value: 0 } },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor; uniform float uBand; uniform float uEnv;
        varying vec2 vUv;
        void main(){
          float core = smoothstep(0.5, 0.0, abs(vUv.x - 0.5)); // bright along axis
          float band = smoothstep(0.22, 0.0, abs(vUv.y - uBand)); // travelling pulse
          float b = (0.4 + band * 2.0) * uEnv * (0.45 + 0.55 * core);
          gl_FragColor = vec4(uColor * b, b);
        }
      `,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.frustumCulled = false;
    this.scene.add(mesh);
    this.beams.push({ mesh, mat, node, age: 0, dur: 2.8, pinged: false });

    // "Sending" beat: a small ring pulses at the orb.
    this._ping(ORIGIN, color, 0.5, 1.3, 0.8);
  }

  // Spawn an expanding ring ping.
  _ping(pos, color, s0, s1, dur) {
    const mat = new THREE.SpriteMaterial({
      map: this.ringTex, color: color.clone(), transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, opacity: 1,
    });
    const sp = new THREE.Sprite(mat);
    sp.position.copy(pos);
    sp.scale.setScalar(s0);
    this.scene.add(sp);
    this.pings.push({ sp, mat, age: 0, dur, s0, s1 });
  }

  // Faint pulse wave rippling out from the orb (thinking).
  pulse(color = new THREE.Color('#8b5cf6')) {
    this._ping(ORIGIN, color, 1.2, 3.4, 2.4);
    // mark it faint
    const p = this.pings[this.pings.length - 1];
    p.faint = true;
  }

  update(dt) {
    // Beams.
    for (let i = this.beams.length - 1; i >= 0; i--) {
      const b = this.beams[i];
      b.age += dt;
      const p = b.age / b.dur;
      const target = b.node.group.position;

      // Orient + stretch the cylinder from orb to the agent's live position.
      _dir.copy(target).sub(ORIGIN);
      const len = _dir.length();
      _mid.copy(target).multiplyScalar(0.5);
      b.mesh.position.copy(_mid);
      _q.setFromUnitVectors(_up, _dir.clone().normalize());
      b.mesh.quaternion.copy(_q);
      b.mesh.scale.set(1, len, 1);

      // Pulse races out (0→1) then back (1→0); envelope fades in/out.
      const band = p < 0.5 ? p * 2 : 1 - (p - 0.5) * 2;
      b.mat.uniforms.uBand.value = band;
      b.mat.uniforms.uEnv.value = Math.sin(p * Math.PI);

      // Agent flares, peaking mid-flight.
      b.node.flare = Math.sin(p * Math.PI);

      // At the peak, ping expands at the agent like a sonar ping.
      if (!b.pinged && p >= 0.5) {
        b.pinged = true;
        this._ping(target, b.node.color, 0.6, 2.2, 1.1);
      }

      if (p >= 1) {
        b.node.flare = 0;
        this.scene.remove(b.mesh);
        b.mesh.geometry.dispose();
        b.mat.dispose();
        this.beams.splice(i, 1);
      }
    }

    // Pings.
    for (let i = this.pings.length - 1; i >= 0; i--) {
      const g = this.pings[i];
      g.age += dt;
      const p = g.age / g.dur;
      const s = g.s0 + (g.s1 - g.s0) * smoothstep(0, 1, p);
      g.sp.scale.setScalar(s);
      g.mat.opacity = (1 - p) * (g.faint ? 0.25 : 0.85);
      if (p >= 1) {
        this.scene.remove(g.sp);
        g.mat.dispose();
        this.pings.splice(i, 1);
      }
    }
  }

  dispose() {
    for (const b of this.beams) { this.scene.remove(b.mesh); b.mesh.geometry.dispose(); b.mat.dispose(); }
    for (const g of this.pings) { this.scene.remove(g.sp); g.mat.dispose(); }
    this.beams = []; this.pings = [];
    this.ringTex.dispose();
  }
}
