// Transport: how the scene learns the agent's state and activity.
//
// If window.AETHER_WS is set, we connect that WebSocket and map incoming
// messages onto the scene. Otherwise we run a small DEMO DRIVER that scripts a
// lifelike sequence (listening → thinking + dispatch → speaking → idle) so the
// interface is alive without any backend.
//
// Message shapes the scene understands (also reusable over SSE/polling — just
// call transport.handle(msg) yourself):
//   { type: 'state',    state: 'listening' }
//   { type: 'dispatch', agent: 'scout' }
//   { type: 'working',  agent: 'scout', on: true }
//   { type: 'agent:add', agent: { id, name, specialty, color, orbit? } }

export class Transport {
  constructor(app, { url } = {}) {
    this.app = app;
    this.ws = null;
    this.demo = null;
    if (url) this._connect(url);
    else { this.demo = new DemoDriver(app); this.demo.start(); }
  }

  _connect(url) {
    try {
      this.ws = new WebSocket(url);
      this.ws.onmessage = (e) => {
        try { this.handle(JSON.parse(e.data)); } catch { /* ignore bad frames */ }
      };
      // If the socket can't be established, fall back to the demo driver.
      this.ws.onerror = () => { if (!this.demo) { this.demo = new DemoDriver(this.app); this.demo.start(); } };
    } catch {
      this.demo = new DemoDriver(this.app);
      this.demo.start();
    }
  }

  // Route a single event onto the scene.
  handle(msg) {
    if (!msg || !msg.type) return;
    switch (msg.type) {
      case 'state':     this.app.setState(msg.state); break;
      case 'dispatch':  this.app.dispatch(msg.agent); break;
      case 'working':   this.app.setWorking(msg.agent, !!msg.on); break;
      case 'agent:add': this.app.addAgent(msg.agent); break;
      default: break;
    }
  }

  update(dt) { if (this.demo) this.demo.update(dt); }

  dispose() { if (this.ws) this.ws.close(); }
}

// A scripted, looping timeline that exercises every state + reaction.
class DemoDriver {
  constructor(app) {
    this.app = app;
    this.running = false;
    this.i = -1;
    this.timer = 0;
    this.steps = [
      { dur: 3.5, run: (a) => a.setState('listening') },
      { dur: 4.5, run: (a) => { a.setState('processing'); a.dispatch('scout'); a.setWorking('scout', true); } },
      { dur: 5.0, run: (a) => { a.setWorking('scout', false); a.setState('speaking'); a.dispatch('forge'); a.setWorking('forge', true); } },
      { dur: 3.0, run: (a) => { a.setWorking('forge', false); a.setState('idle'); } },
      { dur: 3.5, run: (a) => { a.setState('listening'); a.dispatch('aegis'); a.setWorking('aegis', true); } },
      { dur: 4.5, run: (a) => { a.setState('processing'); } },
      { dur: 4.0, run: (a) => { a.setWorking('aegis', false); a.setState('speaking'); } },
      { dur: 2.5, run: (a) => a.setState('idle') },
    ];
  }

  start() { this.running = true; this.timer = 0.4; }

  update(dt) {
    if (!this.running) return;
    this.timer -= dt;
    if (this.timer > 0) return;
    this.i = (this.i + 1) % this.steps.length;
    const step = this.steps[this.i];
    this.timer = step.dur;
    step.run(this.app);
  }

  stop() { this.running = false; }
}
