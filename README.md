# Trillion — Voice-First AI Assistant UI

A luminous teal orb floating in a dark cosmic void, wrapped in a glass-morphism
shell, with a big friendly mic button at the bottom. Built from the three
"build your own voice-first UI" prompts and combined into one cohesive
interface.

## Run it

It's a static site — no build step. Just serve the folder over HTTP (a plain
`file://` open won't work because of ES module imports):

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

## What's inside

| File | Prompt | What it does |
|------|--------|--------------|
| `scene.js` | **1. Luminous Orb + Cosmic Background** | Full-viewport Three.js scene: noise-shader nebula (teal/purple/blue wisps), twinkling starfield, and a teal orb with three additive glow layers (atmospheric bloom → halo → inner core) plus `UnrealBloomPass` post-processing. Exposes `uVoiceBright` via `window.trillionScene.setVoiceBright(0..1)` and a ~4s idle breathing pulse. |
| `styles.css` + `index.html` | **2. Glass Shell** | 56px frosted header with status dot (idle → listening → processing), a collapsible 260px right-side activity panel (Inbox / Scout / Flux / Relay) whose entries slide in, and floating response cards with a teal accent bar and gentle float. |
| `ui.js` + `index.html` | **3. Bottom Mic Bar** | A 64px circular mic button that swaps mic ↔ stop, glows with an expanding pulse ring while listening, and dispatches a `trillion:mic-toggle` event. |

## How it's wired together

The mic button doesn't just animate — it requests microphone access and feeds
live audio amplitude (RMS) into the orb's `uVoiceBright` uniform, so the orb
brightens and swells when you speak. If the mic is denied or unavailable, a
synthetic driver keeps the orb reacting so the demo stays self-contained.

## Design tokens

- Background `#0E0F13` · Surface `#16171D` · Accent `#2DD4A8`
- Fonts: Inter (UI), JetBrains Mono (numbers/timestamps)
- Easing everywhere: `cubic-bezier(0.16, 1, 0.3, 1)`

## Controls

- **Click the mic** (or press **Space**) to toggle listening.
- **Click the chevron** on the activity panel to collapse it.
