# Donald UI — Golden Amber Orb

A Next.js web interface for the D.O.N.A.L.D. agent, featuring an animated golden amber orb UI with interactive voice states.

## Setup

```bash
cd web
npm install
# or yarn install
```

## Development

```bash
npm run dev
# or yarn dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser to see the interface.

## Building

```bash
npm run build
npm start
```

## Connecting to the Donald gateway

The orb is wired to the gateway: type in the box and hit Enter → it POSTs to
`/gw/api/chat`, shows Donald's reply, and plays the ElevenLabs voice if the
gateway returned one. `next.config.js` proxies `/gw/*` to the gateway
(`GATEWAY_URL`, default `http://127.0.0.1:8765`) **server-side**, so the gateway
stays bound to localhost — no CORS, nothing public.

Run the gateway first (see `gateway/README.md`), then `npm run dev`. If the app
and gateway run on different hosts, set `GATEWAY_URL` before starting.

## Features

- **Golden Amber Orb**: Responsive canvas-based animation with dynamic particle effects
- **State Transitions**: Visual feedback for idle, listening, thinking, and speaking states
- **Interactive**: Click the orb to trigger conversation sequences
- **Boot Animation**: Animated startup sequence with progress bar
- **Responsive**: Adapts to screen size with proper DPI scaling
