import * as THREE from 'three';
import { generateAvatarTexture, makeGlowTexture, tryLoadImage } from './avatar.js';
import { AVATAR_BASE } from './agents.js';
import { smoothstep, clamp, damp, isMobile } from './util.js';

const _v = new THREE.Vector3();

// Pulls an agent off its orbit toward a panel: in quickly, out slowly.
class Dock {
  constructor(targetFn) {
    this.targetFn = targetFn; // () => THREE.Vector3 | null  (panel → world)
    this.active = true;
    this.amount = 0;
  }
  release() { this.active = false; }
  apply(pos, dt) {
    // Snappy arrival (lambda 5), graceful return (lambda 1.2).
    this.amount = damp(this.amount, this.active ? 1 : 0, this.active ? 5.0 : 1.2, dt);
    const tgt = this.targetFn();
    if (tgt) {
      const e = this.amount * this.amount * (3 - 2 * this.amount);
      pos.lerp(tgt, e);
    }
    return this.amount;
  }
  get done() { return !this.active && this.amount < 0.01; }
}

// One sub-agent's visual: an orbiting avatar sprite, a soft additive glow
// behind it, and a DOM label that tracks its on-screen position.
class AgentNode {
  constructor(def, scene, labelRoot) {
    this.def = def;
    this.color = new THREE.Color(def.color);
    this.breathePhase = def.orbit.phase * 1.7;

    // Reaction state (driven in Tier 5).
    this.flare = 0;          // dispatch flare 0..1 (set by Effects)
    this.working = 0;        // eased working-pulse intensity 0..1
    this.workingTarget = 0;
    this.dock = null;        // docking controller

    this.group = new THREE.Group();

    // Faint tether line from the orb to this agent while docked.
    const tGeo = new THREE.BufferGeometry();
    tGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    this.tether = new THREE.Line(tGeo, new THREE.LineBasicMaterial({
      color: this.color, transparent: true, opacity: 0,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    this.tether.frustumCulled = false;

    const glowTex = makeGlowTexture(def.color);
    this.glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTex, color: 0xffffff, transparent: true, opacity: 0.6,
      blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false,
    }));
    this.glow.scale.setScalar(1.15);
    this.group.add(this.glow);

    this.avatarMat = new THREE.SpriteMaterial({
      map: generateAvatarTexture(def), transparent: true, opacity: 1,
      depthWrite: false, depthTest: false,
    });
    this.avatar = new THREE.Sprite(this.avatarMat);
    this.avatar.scale.setScalar(0.46);
    this.group.add(this.avatar);

    scene.add(this.group);
    scene.add(this.tether);

    // Try to upgrade to a real image (explicit URL or convention path).
    const url = def.avatar || (AVATAR_BASE ? `${AVATAR_BASE}/${def.id}.png` : null);
    tryLoadImage(url, (tex) => { this.avatarMat.map = tex; this.avatarMat.needsUpdate = true; });

    // DOM label — name on top, specialty beneath. Hidden until first placed.
    this.label = document.createElement('div');
    this.label.className = 'agent-label';
    this.label.innerHTML =
      `<span class="al-name"></span><span class="al-spec"></span>`;
    this.label.querySelector('.al-name').textContent = def.name;
    this.label.querySelector('.al-spec').textContent = def.specialty;
    this.label.style.setProperty('--accent', def.color);
    this.label.style.visibility = 'hidden';
    labelRoot.appendChild(this.label);
    this._shown = false;
  }

  // World position on the tilted orbit at time t.
  position(t, reducedMotion) {
    const o = this.def.orbit;
    const a = reducedMotion ? o.phase : o.phase + t * o.speed;
    // Circle in the XZ plane...
    const x = Math.cos(a) * o.radius;
    const z = Math.sin(a) * o.radius;
    // ...then tilt the plane (alternating directions via o.dir).
    const tl = o.tilt * o.dir;
    const y = -z * Math.sin(tl);
    const zz = z * Math.cos(tl);
    return _v.set(x, y, zz);
  }

  dispose() {
    this.glow.material.map.dispose();
    this.glow.material.dispose();
    this.avatarMat.map.dispose();
    this.avatarMat.dispose();
    this.tether.geometry.dispose();
    this.tether.material.dispose();
    this.tether.parent && this.tether.parent.remove(this.tether);
    this.group.parent && this.group.parent.remove(this.group);
    this.label.remove();
  }
}

export class Constellation {
  constructor(scene, camera, labelRoot) {
    this.scene = scene;
    this.camera = camera;
    this.labelRoot = labelRoot;
    this.nodes = [];
    this.byId = new Map();
    this.reducedMotion = false;
    this.enabled = !isMobile(); // hidden entirely on small mobile screens
    labelRoot.style.display = this.enabled ? '' : 'none';
  }

  add(def) {
    if (!this.enabled) return null;
    const node = new AgentNode(def, this.scene, this.labelRoot);
    this.nodes.push(node);
    this.byId.set(def.id, node);
    return node;
  }

  get(id) { return this.byId.get(id); }

  // Mark an agent as actively working (steady pulsing halo).
  setWorking(id, on) {
    const n = this.byId.get(id);
    if (n) n.workingTarget = on ? 1 : 0;
  }

  // Dock an agent near a panel. targetFn returns a world-space Vector3 (or
  // null to just pulse in orbit). Re-docking refreshes the target.
  dock(id, targetFn) {
    const n = this.byId.get(id);
    if (!n) return;
    if (n.dock) { n.dock.targetFn = targetFn; n.dock.active = true; }
    else n.dock = new Dock(targetFn);
  }

  undock(id) {
    const n = this.byId.get(id);
    if (n && n.dock) n.dock.release();
  }

  update(dt, t, sizePx) {
    if (!this.enabled) return;
    const { width: w, height: h } = sizePx;

    for (const node of this.nodes) {
      // Ease the working-pulse intensity toward its target.
      node.working = damp(node.working, node.workingTarget, 3.0, dt);

      const pos = node.position(t, this.reducedMotion).clone();

      // Docking (Tier 5) can pull the node off its orbit toward a panel.
      let dockAmt = 0;
      if (node.dock) {
        dockAmt = node.dock.apply(pos, dt);
        if (node.dock.done) node.dock = null;
      }

      node.group.position.copy(pos);

      // Tether from orb to a docked agent, fading in with the dock.
      if (dockAmt > 0.01) {
        const a = node.tether.geometry.attributes.position;
        a.setXYZ(0, 0, 0, 0); a.setXYZ(1, pos.x, pos.y, pos.z); a.needsUpdate = true;
        node.tether.material.opacity = dockAmt * 0.28;
      } else {
        node.tether.material.opacity = 0;
      }

      // frontness: 1 when near the camera, 0 when on the far side of the orbit.
      const front = smoothstep(-node.def.orbit.radius, node.def.orbit.radius, pos.z);

      // While working, a steady extra pulse on top of everything.
      const workPulse = node.working * (0.5 + 0.5 * Math.sin(t * 3.2 + node.breathePhase));

      // Breathing glow, slightly out of phase per agent (+ Tier-5 reactions).
      const breathe = 0.5 + 0.5 * Math.sin(t * 0.9 + node.breathePhase);
      const baseGlow = 0.42 + 0.22 * breathe;
      const glowOpacity = baseGlow + node.flare * 0.9 + workPulse * 0.6;
      node.glow.material.opacity = glowOpacity * (0.45 + 0.55 * front);
      // Docked agents hold a calm, steady size; orbiting ones flare/pulse.
      const calm = 1 - 0.55 * dockAmt;
      const glowScale = 1.15 + (node.flare * 0.9 + workPulse * 0.3) * calm
        + 0.06 * breathe;
      node.glow.scale.setScalar(glowScale);
      node.avatar.scale.setScalar(0.46 + node.flare * 0.22 * calm);
      node.avatarMat.opacity = 0.55 + 0.45 * front;

      // --- project to screen for the DOM label ---
      _v.copy(pos).project(this.camera);
      const behindCamera = _v.z > 1;
      const sx = (_v.x * 0.5 + 0.5) * w;
      const sy = (-_v.y * 0.5 + 0.5) * h;

      // Occlusion: hide when directly behind the orb silhouette.
      const radial = Math.hypot(pos.x, pos.y);
      const occluded = pos.z < 0 ? smoothstep(0.7, 1.45, radial) : 1;
      let opacity = (0.18 + 0.82 * front) * occluded;
      if (behindCamera) opacity = 0;

      const el = node.label;
      if (!behindCamera) {
        el.style.transform =
          `translate(-50%, 0) translate(${sx.toFixed(1)}px, ${(sy + 26).toFixed(1)}px)`;
        el.style.opacity = clamp(opacity, 0, 1).toFixed(3);
        el.style.zIndex = String(Math.round(front * 100) + 1); // stack by depth
        if (!node._shown) { el.style.visibility = 'visible'; node._shown = true; }
      } else {
        el.style.opacity = '0';
      }
    }
  }

  setReducedMotion(on) { this.reducedMotion = on; }

  dispose() {
    for (const n of this.nodes) n.dispose();
    this.nodes = [];
    this.byId.clear();
  }
}
