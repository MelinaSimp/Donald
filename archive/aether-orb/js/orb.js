import * as THREE from 'three';
import { simplexNoise3D } from './lib/noise.glsl.js';
import { damp, dampColor } from './util.js';

// The orb: a finely-subdivided wireframe icosahedron whose surface is
// continuously displaced by drifting noise (it "breathes"), shaded with a
// fresnel rim glow, wrapped in a soft additive glow shell.
//
// The orb never reads state directly. Each frame main.js hands it a "mood"
// (a bundle of targets); the orb eases every uniform toward that mood so a
// state change feels like settling into a new temperament, never a hard cut.

export class Orb {
  constructor() {
    this.group = new THREE.Group();

    // Detail 6 → ~5k verts: smooth enough to ripple, light enough to be cheap.
    const geo = new THREE.IcosahedronGeometry(1, 6);

    this.uniforms = {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color('#ff8a3d') },
      uRimColor: { value: new THREE.Color('#ffd9a0') },
      uDisplaceAmp: { value: 0.12 },
      uNoiseScale: { value: 1.6 },
      uNoiseSpeed: { value: 0.35 },
      uBrightness: { value: 0.55 },
      uRimPower: { value: 2.2 },
      uAudioLevel: { value: 0 }, // overall loudness (Tier 3)
      uAudioBass: { value: 0 },  // bass energy (Tier 3)
    };

    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      transparent: true,
      wireframe: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      vertexShader: /* glsl */ `
        ${simplexNoise3D}
        uniform float uTime;
        uniform float uDisplaceAmp;
        uniform float uNoiseScale;
        uniform float uNoiseSpeed;
        uniform float uAudioLevel;
        uniform float uAudioBass;
        varying float vDisplace;
        varying vec3 vNormal;
        varying vec3 vViewDir;

        void main(){
          vec3 p = normal * uNoiseScale + uTime * uNoiseSpeed;
          float n = fbm(p);
          // A second, slower layer makes the breathing feel organic.
          n += 0.5 * fbm(normal * (uNoiseScale * 0.5) - uTime * uNoiseSpeed * 0.6);
          float amp = uDisplaceAmp * (1.0 + uAudioLevel * 2.2 + uAudioBass * 1.4);
          float disp = n * amp;
          vDisplace = n;
          vec3 displaced = position + normal * disp;

          vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vViewDir = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor;
        uniform vec3 uRimColor;
        uniform float uBrightness;
        uniform float uRimPower;
        varying float vDisplace;
        varying vec3 vNormal;
        varying vec3 vViewDir;

        void main(){
          // Fresnel: edges facing away from the camera glow brighter,
          // giving the translucent energy-field look.
          float fres = pow(1.0 - max(dot(vNormal, vViewDir), 0.0), uRimPower);
          vec3 col = mix(uColor, uRimColor, fres);
          float ridge = 0.5 + 0.5 * vDisplace; // crests read a touch brighter
          float intensity = uBrightness * (0.35 + 0.65 * fres) * (0.7 + 0.5 * ridge);
          gl_FragColor = vec4(col * intensity, intensity);
        }
      `,
    });

    this.mesh = new THREE.Mesh(geo, this.material);
    this.group.add(this.mesh);

    // Soft glow shell — a larger backside sphere with a fresnel falloff so it
    // pools a faint colored halo behind/around the orb.
    this.glowUniforms = {
      uColor: { value: new THREE.Color('#ff8a3d') },
      uIntensity: { value: 0.5 },
      uPower: { value: 2.0 },
    };
    const glowMat = new THREE.ShaderMaterial({
      uniforms: this.glowUniforms,
      transparent: true,
      side: THREE.FrontSide, // rim-only halo (bright at silhouette, clear through center)
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      vertexShader: /* glsl */ `
        varying vec3 vNormal;
        varying vec3 vViewDir;
        void main(){
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vViewDir = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor;
        uniform float uIntensity;
        uniform float uPower;
        varying vec3 vNormal;
        varying vec3 vViewDir;
        void main(){
          float fres = pow(1.0 - max(dot(vNormal, vViewDir), 0.0), uPower);
          gl_FragColor = vec4(uColor * fres * uIntensity, fres * uIntensity);
        }
      `,
    });
    this.glow = new THREE.Mesh(new THREE.IcosahedronGeometry(1.32, 5), glowMat);
    this.group.add(this.glow);

    // Live (eased) animation state.
    this.rotSpeed = 0.12;
    this.spinExtra = 0;
    this.scale = 1;
  }

  // Ease every uniform toward the supplied mood. lambda governs the shared
  // rhythm — keep it the same everywhere so the whole scene breathes together.
  update(dt, t, mood, audio) {
    const u = this.uniforms;
    u.uTime.value = t;

    const L = 2.4; // shared easing responsiveness (~1s settle)
    dampColor(u.uColor.value, mood.color, L, dt);
    dampColor(u.uRimColor.value, mood.rimColor, L, dt);
    dampColor(this.glowUniforms.uColor.value, mood.color, L, dt);

    u.uDisplaceAmp.value = damp(u.uDisplaceAmp.value, mood.displace, L, dt);
    u.uNoiseSpeed.value = damp(u.uNoiseSpeed.value, mood.churn, L, dt);
    u.uBrightness.value = damp(u.uBrightness.value, mood.brightness, L, dt);
    u.uRimPower.value = damp(u.uRimPower.value, mood.rimPower, L, dt);
    this.glowUniforms.uIntensity.value = damp(
      this.glowUniforms.uIntensity.value, mood.halo, L, dt);

    // Audio feeds surface displacement and a subtle size pulse.
    u.uAudioLevel.value = audio ? audio.level : 0;
    u.uAudioBass.value = audio ? audio.bass : 0;

    this.rotSpeed = damp(this.rotSpeed, mood.spin, L, dt);
    this.spinExtra = damp(this.spinExtra, mood.spinExtra || 0, L, dt);

    // Mostly around the vertical axis, with a slight constant tilt wobble.
    this.mesh.rotation.y += (this.rotSpeed + this.spinExtra) * dt;
    this.mesh.rotation.x = Math.sin(t * 0.15) * 0.12;
    this.glow.rotation.copy(this.mesh.rotation);

    // Size pulse: mood baseline + audio + a gentle breath.
    const audioPulse = audio ? audio.level * mood.pulse : 0;
    const breath = 1 + Math.sin(t * 0.8) * 0.012;
    const targetScale = (mood.size + audioPulse) * breath;
    this.scale = damp(this.scale, targetScale, 6.0, dt);
    this.group.scale.setScalar(this.scale);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.material.dispose();
    this.glow.geometry.dispose();
    this.glow.material.dispose();
  }
}
