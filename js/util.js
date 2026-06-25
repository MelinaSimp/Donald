// Shared helpers. The single most important rule of this whole interface:
// NOTHING SNAPS. Every visual property eases toward its target every frame.

// Frame-rate independent exponential smoothing toward a target.
// `lambda` is the responsiveness (higher = snappier). dt in seconds.
export function damp(current, target, lambda, dt) {
  return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

// Same easing for a THREE.Color in place.
export function dampColor(color, target, lambda, dt) {
  const k = 1 - Math.exp(-lambda * dt);
  color.r += (target.r - color.r) * k;
  color.g += (target.g - color.g) * k;
  color.b += (target.b - color.b) * k;
  return color;
}

// Asymmetric smoothing: jump up fast, fall away slowly. Used for audio levels
// so the orb leaps to life on a loud syllable and eases back down gently.
export function dampAsym(current, target, lambdaUp, lambdaDown, dt) {
  const lambda = target > current ? lambdaUp : lambdaDown;
  return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const smoothstep = (e0, e1, x) => {
  const t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
};

// Mobile / reduced-motion / size helpers.
export const isMobile = () =>
  matchMedia('(max-width: 720px), (pointer: coarse)').matches;
export const prefersReducedMotion = () =>
  matchMedia('(prefers-reduced-motion: reduce)').matches;

// Deterministic pseudo-random so the scene looks identical run to run
// (no Math.random in hot paths — keeps the field stable).
export function makeRng(seed = 1) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}
