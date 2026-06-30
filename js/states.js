import * as THREE from 'three';

// Each state is a target "mood" the orb eases toward. The characters below
// match the brief; everything is tuned around an ORANGE active accent, with
// LISTENING pushed to a brighter gold-amber + oversized halo so it still reads
// as unmistakably distinct from the orange resting/speaking glow.
//
// Fields:
//   color/rimColor — body and fresnel-rim hues
//   displace       — surface noise amplitude
//   churn          — noise drift speed (how fast it roils)
//   brightness     — overall emissive strength
//   rimPower       — fresnel sharpness (low = soft full glow, high = thin rim)
//   halo           — glow-shell intensity
//   spin           — base rotation speed
//   spinExtra      — additional spin (speaking gets a little kick)
//   size           — baseline scale
//   pulse          — how much audio loudness pulses the size
//   bgGlow         — how brightly the background glow pools behind the orb
//   rings          — whether the processing "helix" rings are present
//   cycle          — optional {a,b,speed} hue oscillation (processing)

const C = (hex) => new THREE.Color(hex);

export function buildStates(accent = '#ff8a3d') {
  const accentCol = C(accent);
  const rim = accentCol.clone().lerp(C('#ffffff'), 0.55);

  return {
    idle: {
      color: accentCol.clone().multiplyScalar(0.6),
      rimColor: rim.clone().multiplyScalar(0.7),
      displace: 0.10, churn: 0.25, brightness: 0.40, rimPower: 2.6,
      halo: 0.35, spin: 0.10, spinExtra: 0, size: 1.0, pulse: 0.04,
      bgGlow: 0.5, rings: false,
    },
    listening: {
      // The one warm beacon: bright gold-amber, high energy, big halo.
      color: C('#ffb02e'),
      rimColor: C('#fff0c2'),
      displace: 0.14, churn: 0.55, brightness: 0.95, rimPower: 2.0,
      halo: 0.95, spin: 0.18, spinExtra: 0, size: 1.04, pulse: 0.10,
      bgGlow: 0.9, rings: false,
    },
    processing: {
      // Dim body, faster churn, hue cycling teal↔purple. Rings are the event.
      color: C('#23c4b8'),
      rimColor: C('#bfeee8'),
      displace: 0.13, churn: 0.95, brightness: 0.45, rimPower: 2.8,
      halo: 0.55, spin: 0.30, spinExtra: 0, size: 0.98, pulse: 0.05,
      bgGlow: 0.85, rings: true,
      cycle: { a: C('#23c4b8'), b: C('#8b5cf6'), speed: 0.45 },
    },
    speaking: {
      // Bright and lively, dramatic voice-driven deformation, size pulse, kick.
      color: accentCol.clone(),
      rimColor: rim.clone(),
      displace: 0.22, churn: 0.7, brightness: 1.0, rimPower: 1.9,
      halo: 0.85, spin: 0.16, spinExtra: 0.25, size: 1.02, pulse: 0.16,
      bgGlow: 1.0, rings: false,
    },
    error: {
      color: C('#ff3b30'),
      rimColor: C('#ff9a93'),
      displace: 0.05, churn: 0.08, brightness: 0.7, rimPower: 3.4,
      halo: 0.5, spin: 0.02, spinExtra: 0, size: 0.97, pulse: 0.0,
      bgGlow: 0.6, rings: false,
    },
  };
}

export const STATE_NAMES = ['idle', 'listening', 'processing', 'speaking', 'error'];
