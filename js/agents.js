// The sub-agents — the floating constellation. Each is a small bundle your
// backend can serve, or that you hardcode here. Three plausible defaults so
// the constellation is never empty (from the interview).
//
// orbit params spread them out: different radius, speed, starting phase, and
// ALTERNATING tilt directions so their paths sit in different planes and never
// move in lockstep. Radii sit in a safe band — clearly outside the orb's glow
// and the Tier-5 rings, but inside the visible frame.

export const AGENTS = [
  {
    id: 'scout', name: 'Scout', specialty: 'Research & retrieval',
    color: '#22d3ee', // cyan
    orbit: { radius: 2.05, speed: 0.20, phase: 0.0, tilt: 0.34, dir: 1 },
  },
  {
    id: 'forge', name: 'Forge', specialty: 'Builds & code',
    color: '#a855f7', // violet
    orbit: { radius: 2.35, speed: -0.15, phase: 2.1, tilt: 0.42, dir: -1 },
  },
  {
    id: 'aegis', name: 'Aegis', specialty: 'Support & guardrails',
    color: '#34d399', // green
    orbit: { radius: 2.2, speed: 0.17, phase: 4.3, tilt: 0.26, dir: 1 },
  },
];

// Optional base path for convention avatars. If set (e.g. './avatars'), each
// agent without an explicit `avatar` URL will try `${AVATAR_BASE}/${id}.png`
// before falling back to a generated avatar. Left null so a cold load stays
// clean (no 404s) and every agent still looks finished via generation.
export const AVATAR_BASE = null;
