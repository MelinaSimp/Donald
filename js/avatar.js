import * as THREE from 'three';

// Avatar textures. Three-step fallback so a brand-new agent always looks
// finished with zero art:
//   1. explicit `agent.avatar` image URL, else
//   2. a convention path `${AVATAR_BASE}/${id}.png`, else
//   3. a generated avatar — a soft colored halo, a disc fading from a dark
//      core out to the accent color, a thin rim, and the agent's initial.
//
// We ALWAYS generate immediately so the constellation is polished on first
// frame, then asynchronously upgrade to a real image if one loads.

export function generateAvatarTexture(agent) {
  const S = 256;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const ctx = c.getContext('2d');
  const cx = S / 2, cy = S / 2;
  const accent = agent.color || '#ffffff';

  // Disc: dark core → accent at the edge.
  const disc = ctx.createRadialGradient(cx, cy, S * 0.05, cx, cy, S * 0.42);
  disc.addColorStop(0, shade(accent, -0.78));
  disc.addColorStop(0.65, shade(accent, -0.35));
  disc.addColorStop(1, accent);
  ctx.fillStyle = disc;
  ctx.beginPath();
  ctx.arc(cx, cy, S * 0.42, 0, Math.PI * 2);
  ctx.fill();

  // Thin bright rim.
  ctx.lineWidth = S * 0.025;
  ctx.strokeStyle = shade(accent, 0.4);
  ctx.beginPath();
  ctx.arc(cx, cy, S * 0.42, 0, Math.PI * 2);
  ctx.stroke();

  // Initial.
  ctx.fillStyle = '#ffffff';
  ctx.font = `600 ${S * 0.34}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.shadowColor = accent;
  ctx.shadowBlur = S * 0.08;
  ctx.fillText((agent.name || '?')[0].toUpperCase(), cx, cy + S * 0.02);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// Radial soft-glow sprite texture (additive light source behind the avatar).
export function makeGlowTexture(color = '#ffffff') {
  const S = 256;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  const rgb = hexToRgb(color);
  g.addColorStop(0, `rgba(${rgb.r},${rgb.g},${rgb.b},0.9)`);
  g.addColorStop(0.4, `rgba(${rgb.r},${rgb.g},${rgb.b},0.35)`);
  g.addColorStop(1, `rgba(${rgb.r},${rgb.g},${rgb.b},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// Try to upgrade to a real image; calls onTexture(tex) only on success.
export function tryLoadImage(url, onTexture) {
  if (!url) return;
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    const tex = new THREE.Texture(img);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;
    onTexture(tex);
  };
  img.onerror = () => {}; // keep the generated avatar; no broken-image box
  img.src = url;
}

// --- small color helpers ---
function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function shade(hex, amt) {
  const { r, g, b } = hexToRgb(hex);
  const f = (v) => Math.round(amt < 0 ? v * (1 + amt) : v + (255 - v) * amt);
  return `rgb(${f(r)},${f(g)},${f(b)})`;
}
