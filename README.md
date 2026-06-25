# Aether — a living cosmic interface for an AI agent

A single full-screen 3D scene that gives an AI agent a face: a voice-reactive
orb floating in a procedural deep-space nebula, surrounded by a constellation
of floating sub-agents that orbit the orb, light up when dispatched, and settle
near their panels while they work.

Plain HTML + ES modules + [three.js](https://threejs.org) — **no build step, no
bundler**. three.js is vendored locally (`js/lib/three.module.js`) so the scene
works offline; swap the importmap in `index.html` for a CDN URL if you prefer.

## Run it

Serve the folder over HTTP (ES modules need a server, not `file://`):

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

With no backend, a **demo driver** cycles the scene through every state and
reaction so it's alive immediately.

## The three layers

The interface is three stacked, full-screen layers, composited back-to-front:

| Layer | File(s) | What it draws |
|-------|---------|---------------|
| **Background** (own renderer) | `background.js` | procedural sky — drifting nebula, twinkling stars, orb glow, vignette — plus a faint 3D web of clustered nodes, lines, and dust |
| **Orb** (transparent, own renderer) | `orb.js`, `rings.js`, `effects.js`, `constellation.js` | the breathing wireframe orb + halo, the processing "helix" rings, dispatch beams/pings, and the orbiting sub-agent avatars |
| **Labels** (DOM) | `constellation.js` + `index.html` | plain HTML labels that follow each avatar on screen |

A single animation loop in `main.js` drives everything. The core stylistic
rule: **nothing snaps** — every property eases toward its target each frame via
the shared dampers in `util.js`.

## Controlling it (JS API)

All of these are on `window` for console testing, and on the `CosmicInterface`
instance (`window.cosmic`):

```js
setState('listening')          // idle | listening | processing | speaking | error
dispatch('scout')              // beam + flare + sonar ping at an agent
setWorking('forge', true)      // steady pulse; docks near [data-agent="forge"] if present
setWorking('forge', false)     // stops; agent drifts back to orbit
addAgent({ id:'nova', name:'Nova', specialty:'Live ops', color:'#f59e0b',
           orbit:{ radius:2.1, speed:0.19, phase:1.0, tilt:0.3, dir:-1 } })
setPerformanceMode(true)       // background → low-res, every-other-frame (also: press P)
enableMic()                    // unlock real audio analysis (call from a user gesture)
```

## Wiring to a real backend

Set a WebSocket URL before the module loads and the scene connects to it:

```html
<script>window.AETHER_WS = 'wss://your-server/agent';</script>
```

Messages it understands (see `transport.js`):

```jsonc
{ "type": "state",     "state": "processing" }
{ "type": "dispatch",  "agent": "scout" }
{ "type": "working",   "agent": "scout", "on": true }
{ "type": "agent:add", "agent": { "id": "...", "name": "...", "specialty": "...", "color": "#..." } }
```

Using SSE or polling instead? Just call `aetherEvent(msg)` with the same shapes.

## Voice reactivity

`audio.js` reads **loudness** and **bass** each frame and feeds them to the
orb's surface displacement and size pulse, smoothed asymmetrically (fast attack,
slow release). It auto-selects: real Web Audio when a signal is flowing,
otherwise a synthetic speech-cadence motion so the orb always looks alive.

**iOS note:** iOS Safari is fussy about analysing audio while playing it aloud.
Play the audible audio normally and feed a *silent duplicate* into the analyser
(`attachAudio(el, { silent:true })`), create the AudioContext inside a real
user tap, and use a separate context for the mic. See the comments in
`audio.js`.

## Configuration

- **Agents & accent:** `agents.js` (sub-agent list + orbit params) and the
  `ACCENT` constant in `main.js`.
- **State moods:** `states.js` — each state is a target "mood" the orb eases
  toward. Tuned around an orange active accent with a gold-amber listening state.
- **Avatars:** generated on the fly (`avatar.js`). Drop real images and set
  `AVATAR_BASE` in `agents.js`, or give an agent an explicit `avatar` URL.

## Accessibility & performance

- Respects `prefers-reduced-motion` (sub-agents held still, drift calmed).
- Pauses on tab-hide and WebGL context loss; resumes without a phase jump.
- Constellation and panels hide on small mobile screens; background node/dust
  counts roughly halve on mobile.
