import * as THREE from 'three';
import { damp } from './util.js';

// The "helix": thin glowing rings that fade in around the orb while it's in
// the processing state. Each is tilted differently and rotates at its own
// speed, with a bright pulse travelling around it; the color drifts from teal
// toward purple. These are the focal point of the processing state.

const RING_DEFS = [
  { radius: 1.50, tube: 0.018, tilt: [1.1, 0.2, 0.0], spin: 0.6, pulse: 0.20 },
  { radius: 1.64, tube: 0.015, tilt: [0.3, 1.0, 0.4], spin: -0.45, pulse: 0.31 },
  { radius: 1.78, tube: 0.016, tilt: [0.7, -0.5, 0.9], spin: 0.32, pulse: 0.14 },
];

export class RingSystem {
  constructor(scene) {
    this.group = new THREE.Group();
    scene.add(this.group);
    this.rings = [];
    this.amount = 0; // eased 0→1 with the processing state
    this.colorA = new THREE.Color('#23c4b8');
    this.colorB = new THREE.Color('#8b5cf6');

    for (const def of RING_DEFS) {
      const geo = new THREE.TorusGeometry(def.radius, def.tube, 12, 220);
      const uniforms = {
        uColor: { value: new THREE.Color('#23c4b8') },
        uOpacity: { value: 0 },
        uPulse: { value: 0 },
      };
      const mat = new THREE.ShaderMaterial({
        uniforms,
        transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: /* glsl */ `
          varying vec2 vUv;
          void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor; uniform float uOpacity; uniform float uPulse;
          varying vec2 vUv;
          void main(){
            // distance (around the ring) to the travelling pulse position
            float d = abs(fract(vUv.x - uPulse + 0.5) - 0.5);
            float spot = smoothstep(0.07, 0.0, d);
            // soft across the tube cross-section
            float edge = sin(vUv.y * 3.14159);
            float b = (0.6 + spot * 2.4) * edge;
            gl_FragColor = vec4(uColor * b, uOpacity * b);
          }
        `,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.set(def.tilt[0], def.tilt[1], def.tilt[2]);
      this.group.add(mesh);
      this.rings.push({ mesh, mat, uniforms, def, baseTilt: def.tilt.slice() });
    }
  }

  // active: whether the orb is in processing. t: time.
  update(dt, t, active) {
    this.amount = damp(this.amount, active ? 1 : 0, 2.0, dt);
    // Color drifts teal↔purple.
    const k = 0.5 + 0.5 * Math.sin(t * 0.25);
    for (const r of this.rings) {
      r.uniforms.uColor.value.copy(this.colorA).lerp(this.colorB, k);
      r.uniforms.uOpacity.value = this.amount * 1.15;
      r.uniforms.uPulse.value = (t * r.def.pulse) % 1;
      // own rotation speed, around the ring's tilt
      r.mesh.rotation.z = r.baseTilt[2] + t * r.def.spin;
    }
    this.group.visible = this.amount > 0.01;
  }

  dispose() {
    for (const r of this.rings) { r.mesh.geometry.dispose(); r.mat.dispose(); }
  }
}
