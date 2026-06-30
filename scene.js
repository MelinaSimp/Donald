// ============================================================
// 1. The Luminous Orb + Cosmic Background
//    Three.js scene: drifting nebula, twinkling starfield, and a
//    teal orb with three glow layers + bloom post-processing.
//    Exposes window.trillionScene.setVoiceBright(0..1).
// ============================================================
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const canvas = document.getElementById("scene");
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: false,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x0e0f13, 1);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(
  55,
  window.innerWidth / window.innerHeight,
  0.1,
  100
);
camera.position.z = 6;

// ------------------------------------------------------------
// Nebula — a full-screen quad driven by a noise-based shader.
// Slowly drifting teal / purple / blue wisps over the dark base.
// ------------------------------------------------------------
const nebulaUniforms = {
  uTime: { value: 0 },
  uRes: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
};

const nebula = new THREE.Mesh(
  new THREE.PlaneGeometry(2, 2),
  new THREE.ShaderMaterial({
    depthTest: false,
    depthWrite: false,
    uniforms: nebulaUniforms,
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = vec4(position.xy, 0.0, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec2 vUv;
      uniform float uTime;
      uniform vec2  uRes;

      // hash + value noise + fbm
      vec2 hash(vec2 p){
        p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
        return fract(sin(p) * 43758.5453) * 2.0 - 1.0;
      }
      float noise(vec2 p){
        vec2 i = floor(p);
        vec2 f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(
          mix(dot(hash(i + vec2(0.0,0.0)), f - vec2(0.0,0.0)),
              dot(hash(i + vec2(1.0,0.0)), f - vec2(1.0,0.0)), u.x),
          mix(dot(hash(i + vec2(0.0,1.0)), f - vec2(0.0,1.0)),
              dot(hash(i + vec2(1.0,1.0)), f - vec2(1.0,1.0)), u.x), u.y);
      }
      float fbm(vec2 p){
        float v = 0.0;
        float a = 0.5;
        for (int i = 0; i < 5; i++){
          v += a * noise(p);
          p *= 2.02;
          a *= 0.5;
        }
        return v;
      }

      void main(){
        vec2 uv = vUv;
        vec2 p = (uv - 0.5) * vec2(uRes.x / uRes.y, 1.0);

        float t = uTime * 0.03;
        // two drifting noise fields
        float n1 = fbm(p * 2.2 + vec2(t, -t * 0.6));
        float n2 = fbm(p * 3.6 - vec2(t * 0.4, t));
        float clouds = smoothstep(0.05, 0.75, n1 * 0.7 + n2 * 0.5);

        // palette: teal, purple, blue
        vec3 teal   = vec3(0.176, 0.831, 0.659);
        vec3 purple = vec3(0.40, 0.27, 0.74);
        vec3 blue   = vec3(0.20, 0.36, 0.78);

        vec3 col = mix(purple, blue, smoothstep(-0.2, 0.6, n2));
        col = mix(col, teal, smoothstep(0.2, 0.9, n1));

        // keep it dark + moody: nebula only faintly tints the void
        vec3 base = vec3(0.055, 0.059, 0.075);
        float radial = 1.0 - smoothstep(0.2, 1.1, length(p));
        vec3 finalC = base + col * clouds * 0.16 * (0.5 + radial * 0.7);

        gl_FragColor = vec4(finalC, 1.0);
      }
    `,
  })
);
nebula.frustumCulled = false;
nebula.renderOrder = -10;
scene.add(nebula);

// ------------------------------------------------------------
// Starfield — additive points, gentle twinkle.
// ------------------------------------------------------------
const STAR_COUNT = 1400;
const starPos = new Float32Array(STAR_COUNT * 3);
const starPhase = new Float32Array(STAR_COUNT);
for (let i = 0; i < STAR_COUNT; i++) {
  const r = 14 + Math.random() * 26;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  starPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
  starPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
  starPos[i * 3 + 2] = r * Math.cos(phi) - 10;
  starPhase[i] = Math.random() * Math.PI * 2;
}
const starGeo = new THREE.BufferGeometry();
starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
starGeo.setAttribute("aPhase", new THREE.BufferAttribute(starPhase, 1));

const starMat = new THREE.ShaderMaterial({
  transparent: true,
  depthWrite: false,
  blending: THREE.AdditiveBlending,
  uniforms: { uTime: { value: 0 } },
  vertexShader: /* glsl */ `
    attribute float aPhase;
    uniform float uTime;
    varying float vTw;
    void main(){
      vTw = 0.55 + 0.45 * sin(uTime * 1.6 + aPhase);
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      gl_PointSize = (1.0 + vTw * 1.6) * (300.0 / -mv.z);
      gl_Position = projectionMatrix * mv;
    }
  `,
  fragmentShader: /* glsl */ `
    varying float vTw;
    void main(){
      vec2 c = gl_PointCoord - 0.5;
      float d = length(c);
      float a = smoothstep(0.5, 0.0, d) * vTw;
      gl_FragColor = vec4(vec3(0.85, 0.95, 1.0), a);
    }
  `,
});
const stars = new THREE.Points(starGeo, starMat);
scene.add(stars);

// ------------------------------------------------------------
// The Orb — three additive glow layers + idle breathing pulse,
// brightened by uVoiceBright (driven by mic amplitude in ui.js).
// ------------------------------------------------------------
const ACCENT = new THREE.Color(0x2dd4a8);

const orbUniforms = {
  uTime: { value: 0 },
  uVoiceBright: { value: 0 }, // 0..1, raised from audio amplitude
  uColor: { value: ACCENT },
};

// glow layer factory: a billboarded radial-gradient sprite
function makeGlowLayer(size, intensity, falloff) {
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      ...orbUniforms,
      uIntensity: { value: intensity },
      uFalloff: { value: falloff },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main(){
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec2 vUv;
      uniform float uTime;
      uniform float uVoiceBright;
      uniform float uIntensity;
      uniform float uFalloff;
      uniform vec3  uColor;
      void main(){
        float d = length(vUv - 0.5) * 2.0;
        float idle = 0.5 + 0.5 * sin(uTime * (6.2831 / 4.0)); // ~4s breath
        float bright = uIntensity * (0.82 + idle * 0.18 + uVoiceBright * 0.9);
        float glow = pow(max(0.0, 1.0 - d), uFalloff) * bright;
        gl_FragColor = vec4(uColor * glow, glow);
      }
    `,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), mat);
  return mesh;
}

const orb = new THREE.Group();
// (1) wide soft atmospheric bloom, (2) medium halo, (3) bright inner core
const bloomLayer = makeGlowLayer(7.5, 0.5, 2.2);
const haloLayer = makeGlowLayer(3.6, 1.0, 3.4);
const coreLayer = makeGlowLayer(1.9, 1.7, 6.0);
orb.add(bloomLayer, haloLayer, coreLayer);

// solid-ish inner sphere for body
const coreSphere = new THREE.Mesh(
  new THREE.SphereGeometry(0.55, 48, 48),
  new THREE.ShaderMaterial({
    uniforms: orbUniforms,
    transparent: true,
    blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      varying vec3 vN;
      varying vec3 vView;
      void main(){
        vN = normalize(normalMatrix * normal);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vView = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vN;
      varying vec3 vView;
      uniform vec3  uColor;
      uniform float uVoiceBright;
      uniform float uTime;
      void main(){
        float fres = pow(1.0 - max(0.0, dot(vN, vView)), 2.0);
        float idle = 0.5 + 0.5 * sin(uTime * 1.5708);
        vec3 c = uColor * (0.6 + fres * 1.2 + uVoiceBright * 0.8 + idle * 0.1);
        gl_FragColor = vec4(c, 0.9);
      }
    `,
  })
);
orb.add(coreSphere);
scene.add(orb);

// keep glow layers facing the camera
function faceCamera(mesh) {
  mesh.quaternion.copy(camera.quaternion);
}

// ------------------------------------------------------------
// Bloom post-processing
// ------------------------------------------------------------
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  0.9, // strength
  0.85, // radius
  0.18 // threshold
);
composer.addPass(bloomPass);

// ------------------------------------------------------------
// Voice brightness — smoothed toward a target set externally.
// ------------------------------------------------------------
let voiceTarget = 0;
let voiceCurrent = 0;

window.trillionScene = {
  setVoiceBright(v) {
    voiceTarget = Math.max(0, Math.min(1, v));
  },
};

// ------------------------------------------------------------
// Resize
// ------------------------------------------------------------
function onResize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  renderer.setSize(w, h);
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  nebulaUniforms.uRes.value.set(w, h);
  bloomPass.resolution.set(w, h);
}
window.addEventListener("resize", onResize);

// subtle parallax toward the pointer
let px = 0;
let py = 0;
window.addEventListener("pointermove", (e) => {
  px = (e.clientX / window.innerWidth - 0.5) * 0.3;
  py = (e.clientY / window.innerHeight - 0.5) * 0.3;
});

// ------------------------------------------------------------
// Render loop
// ------------------------------------------------------------
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();

  // smooth voice brightness (fast attack, slow release)
  const rate = voiceTarget > voiceCurrent ? 0.25 : 0.06;
  voiceCurrent += (voiceTarget - voiceCurrent) * rate;

  nebulaUniforms.uTime.value = t;
  starMat.uniforms.uTime.value = t;
  orbUniforms.uTime.value = t;
  orbUniforms.uVoiceBright.value = voiceCurrent;

  faceCamera(bloomLayer);
  faceCamera(haloLayer);
  faceCamera(coreLayer);

  // gentle scale pulse on the core sphere driven by voice
  const s = 1 + voiceCurrent * 0.12 + Math.sin(t * 1.5708) * 0.015;
  coreSphere.scale.setScalar(s);
  orb.rotation.y = t * 0.05;

  stars.rotation.y = t * 0.01;

  camera.position.x += (px - camera.position.x) * 0.04;
  camera.position.y += (-py - camera.position.y) * 0.04;
  camera.lookAt(0, 0, 0);

  composer.render();
}
animate();
