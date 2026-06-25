import * as THREE from 'three';
import { simplexNoise3D } from './lib/noise.glsl.js';
import { damp, dampColor, makeRng, isMobile } from './util.js';

// The cosmic background — its OWN renderer so it can quietly drop to half
// framerate / lower resolution on weak devices while the orb stays crisp.
// Two passes drawn back-to-front:
//   1. The sky   — a full-screen procedural shader (nebula, stars, orb glow).
//   2. The web   — a faint 3D network of clustered nodes, lines and dust.

export class Background {
  constructor(root) {
    const canvas = document.createElement('canvas');
    canvas.className = 'layer bg-layer';
    root.appendChild(canvas);

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false });
    this.renderer.setClearColor(0x000000, 1);
    this.renderer.autoClear = false;
    this.dpr = Math.min(devicePixelRatio, 2);
    this.renderer.setPixelRatio(this.dpr);

    this.mobile = isMobile();
    this.fade = 0;            // eased 0→1 fade-in on load
    this.glowStrength = 0.5;  // eased toward mood.bgGlow
    this.glowColor = new THREE.Color('#ff8a3d');

    this._buildSky();
    this._buildNetwork();

    // Performance mode (driven by Tier 6).
    this.lowRes = false;
    this.frameSkip = false;
    this._frame = 0;
  }

  _buildSky() {
    this.skyScene = new THREE.Scene();
    this.skyCam = new THREE.Camera(); // full-screen triangle, no transforms

    this.skyUniforms = {
      uTime: { value: 0 },
      uAspect: { value: 1 },
      uGlowColor: { value: this.glowColor },
      uGlowStrength: { value: 0.5 },
      uFade: { value: 0 },
    };

    const geo = new THREE.BufferGeometry();
    // Oversized clip-space triangle covering the screen.
    geo.setAttribute('position', new THREE.BufferAttribute(
      new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(
      new Float32Array([0, 0, 2, 0, 0, 2]), 2));

    const mat = new THREE.RawShaderMaterial({
      uniforms: this.skyUniforms,
      depthTest: false, depthWrite: false,
      vertexShader: /* glsl */ `
        attribute vec3 position; attribute vec2 uv;
        varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        ${simplexNoise3D}
        varying vec2 vUv;
        uniform float uTime, uAspect, uGlowStrength, uFade;
        uniform vec3 uGlowColor;

        float hash21(vec2 p){
          p = fract(p * vec2(123.34, 345.45));
          p += dot(p, p + 34.345);
          return fract(p.x * p.y);
        }

        // One twinkling star layer over a grid.
        float starLayer(vec2 uv, float density, float size, float tw, float thresh){
          vec2 g = uv * density;
          vec2 id = floor(g);
          vec2 f = fract(g) - 0.5;
          float h = hash21(id);
          float h2 = hash21(id + 7.1);
          if (h < thresh) return 0.0;
          vec2 off = (vec2(h, h2) - 0.5) * 0.7;
          float d = length(f - off);
          float br = smoothstep(size, 0.0, d);
          float twinkle = 0.45 + 0.55 * sin(uTime * tw + h * 31.4);
          return br * twinkle;
        }

        void main(){
          vec2 uv = vUv;
          vec2 p = (uv - 0.5) * vec2(uAspect, 1.0);
          float r = length(p);

          // Dark base, slightly brighter toward the center.
          vec3 col = mix(vec3(0.030, 0.035, 0.060), vec3(0.006, 0.008, 0.016),
                         smoothstep(0.0, 0.9, r));

          // Drifting nebula clouds — independent layers, directions, colors.
          float n1 = fbm(vec3(p * 1.6 + vec2(uTime * 0.010, uTime * 0.004), uTime * 0.020));
          float n2 = fbm(vec3(p * 2.4 + vec2(-uTime * 0.008, uTime * 0.006), 5.0 + uTime * 0.015));
          float n3 = fbm(vec3(p * 3.1 + vec2(uTime * 0.006, -uTime * 0.009), 9.0 + uTime * 0.012));
          col += vec3(0.06, 0.26, 0.21) * smoothstep(0.05, 0.85, n1) * 0.80; // cool green
          col += vec3(0.34, 0.07, 0.30) * smoothstep(0.20, 0.92, n2) * 0.45; // magenta
          col += vec3(0.07, 0.14, 0.40) * smoothstep(0.10, 0.92, n3) * 0.55; // blue

          // Two star layers — dense+fine and sparse+large.
          float s1 = starLayer(uv * vec2(uAspect, 1.0), 80.0, 0.06, 2.4, 0.86);
          float s2 = starLayer(uv * vec2(uAspect, 1.0) + 3.7, 34.0, 0.10, 1.5, 0.80);
          col += vec3(0.85, 0.92, 1.0) * s1 * 1.1;
          col += vec3(1.0, 0.95, 0.9) * s2 * 1.4;

          // Soft glow pooled behind the orb, in the orb's live color.
          float glow = exp(-r * 3.2) * uGlowStrength;
          col += uGlowColor * glow;

          // Vignette toward the corners keeps the eye centered.
          col *= smoothstep(1.25, 0.25, r);

          gl_FragColor = vec4(col * uFade, 1.0);
        }
      `,
    });

    this.skyMesh = new THREE.Mesh(geo, mat);
    this.skyMesh.frustumCulled = false;
    this.skyScene.add(this.skyMesh);
  }

  _buildNetwork() {
    this.netScene = new THREE.Scene();
    this.netCam = new THREE.PerspectiveCamera(55, 1, 0.1, 100);
    this.netCam.position.set(0, 0, 14);

    this.netGroup = new THREE.Group();
    this.netScene.add(this.netGroup);

    const rng = makeRng(20260625);
    const CLUSTERS = 8;
    const NODES = this.mobile ? 55 : 110;
    const DUST = this.mobile ? 160 : 340;
    const palette = [
      '#2dd4bf', '#22d3ee', '#3b82f6', '#8b5cf6',
      '#ec4899', '#14b8a6', '#6366f1', '#a855f7',
    ].map((h) => new THREE.Color(h));

    // Scatter cluster centers in a deep, wide shell behind the orb.
    const centers = [];
    for (let c = 0; c < CLUSTERS; c++) {
      centers.push(new THREE.Vector3(
        (rng() - 0.5) * 26,
        (rng() - 0.5) * 16,
        -14 - rng() * 18)); // pushed deeper so it reads as faint distance
    }

    // Nodes gathered around cluster centers.
    const nodePos = new Float32Array(NODES * 3);
    const nodeCol = new Float32Array(NODES * 3);
    const nodeVecs = [];
    for (let i = 0; i < NODES; i++) {
      const c = i % CLUSTERS;
      const center = centers[c];
      const v = new THREE.Vector3(
        center.x + (rng() - 0.5) * 4.5,
        center.y + (rng() - 0.5) * 4.5,
        center.z + (rng() - 0.5) * 4.5);
      nodeVecs.push(v);
      v.toArray(nodePos, i * 3);
      const col = palette[c].clone().multiplyScalar(0.6 + rng() * 0.4);
      col.toArray(nodeCol, i * 3);
    }

    const nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePos, 3));
    nodeGeo.setAttribute('color', new THREE.BufferAttribute(nodeCol, 3));
    const nodeMat = new THREE.PointsMaterial({
      size: 0.11, vertexColors: true, transparent: true, opacity: 0.55,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    });
    this.netGroup.add(new THREE.Points(nodeGeo, nodeMat));

    // Thin lines between any two nodes that are close together.
    const linePos = [];
    const lineCol = [];
    const THRESH = 4.2;
    for (let i = 0; i < NODES; i++) {
      for (let j = i + 1; j < NODES; j++) {
        if (nodeVecs[i].distanceTo(nodeVecs[j]) < THRESH) {
          nodeVecs[i].toArray(linePos, linePos.length);
          nodeVecs[j].toArray(linePos, linePos.length);
          const c = palette[i % CLUSTERS].clone().multiplyScalar(0.20);
          lineCol.push(c.r, c.g, c.b, c.r, c.g, c.b);
        }
      }
    }
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePos), 3));
    lineGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(lineCol), 3));
    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.35,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    this.netGroup.add(new THREE.LineSegments(lineGeo, lineMat));

    // Floating dust motes.
    const dustPos = new Float32Array(DUST * 3);
    for (let i = 0; i < DUST; i++) {
      dustPos[i * 3] = (rng() - 0.5) * 30;
      dustPos[i * 3 + 1] = (rng() - 0.5) * 20;
      dustPos[i * 3 + 2] = -2 - rng() * 24;
    }
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    const dustMat = new THREE.PointsMaterial({
      size: 0.05, color: 0x88aacc, transparent: true, opacity: 0.5,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    this.netGroup.add(new THREE.Points(dustGeo, dustMat));

    this._netMats = [nodeMat, lineMat, dustMat];
  }

  setPerformanceMode(on) {
    this.lowRes = on;
    this.frameSkip = on;
    this._resize();
  }

  resize() { this._resize(); }
  _resize() {
    const w = innerWidth, h = innerHeight;
    const scale = this.lowRes ? 0.6 : 1;
    this.renderer.setPixelRatio(this.dpr * scale);
    this.renderer.setSize(w, h, false);
    this.skyUniforms.uAspect.value = w / h;
    this.netCam.aspect = w / h;
    this.netCam.updateProjectionMatrix();
  }

  // mood.bgGlow + the orb's live color drive the glow pooled behind the orb.
  update(dt, t, moodGlow, orbColor) {
    this.fade = damp(this.fade, 1, 1.0, dt); // ~1.5s fade-in
    this.skyUniforms.uTime.value = t;
    this.skyUniforms.uFade.value = this.fade;

    this.glowStrength = damp(this.glowStrength, moodGlow, 2.0, dt);
    this.skyUniforms.uGlowStrength.value = this.glowStrength;
    if (orbColor) dampColor(this.glowColor, orbColor, 2.0, dt);

    // Slow drift of the whole web + a gentle wandering camera.
    this.netGroup.rotation.y = t * 0.012;
    this.netGroup.rotation.x = Math.sin(t * 0.03) * 0.08;
    this.netCam.position.x = Math.sin(t * 0.05) * 0.6;
    this.netCam.position.y = Math.cos(t * 0.04) * 0.4;
    this.netCam.lookAt(0, 0, -10);

    // Performance mode: render the background every other frame.
    this._frame++;
    if (this.frameSkip && this._frame % 2 === 0) return;

    this.renderer.clear();
    this.renderer.render(this.skyScene, this.skyCam);
    this.renderer.render(this.netScene, this.netCam);
  }

  dispose() {
    this.skyMesh.geometry.dispose();
    this.skyMesh.material.dispose();
    this.netGroup.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
    this.renderer.dispose();
  }
}
