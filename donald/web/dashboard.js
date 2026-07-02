// Hermes Command Center — live view of Donald's hands.
// Polls /api/dashboard and re-renders; toggles the kill switch.

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  let paused = false;

  function ago(ts) {
    const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    return `${Math.floor(s / 3600)}h ago`;
  }

  function actionIcon(a) {
    if (a.needs_confirmation) return "⏸";
    return a.ok ? "✓" : "✕";
  }

  function renderStatus(s) {
    const bar = $("statusbar");
    bar.innerHTML = "";
    const chip = (label, val, cls) => {
      const c = el("span", "chip " + (cls || ""));
      c.append(el("b", null, label + " "), el("span", null, val));
      return c;
    };
    bar.append(
      chip("Machine", s.platform),
      chip("Approval", s.approval_mode),
      chip("Computer-use", s.computer_use ? "ON" : "off", s.computer_use ? "on" : ""),
      chip("Dry-run", s.dry_run ? "ON" : "off", s.dry_run ? "warn" : ""),
      chip("Brain", s.has_api_key ? "ready" : "NO KEY", s.has_api_key ? "on" : "bad")
    );
    paused = s.paused;
    const pill = $("pill-paused");
    pill.textContent = paused ? "● HALTED" : "● LIVE";
    pill.className = "pill " + (paused ? "bad" : "on");
    const kb = $("kill");
    kb.textContent = paused ? "▶ Resume" : "■ Stop";
    kb.classList.toggle("engaged", paused);
    document.body.classList.toggle("is-paused", paused);
  }

  function renderFeed(actions) {
    const feed = $("feed");
    feed.innerHTML = "";
    if (!actions.length) {
      feed.append(el("p", "empty", "No actions yet. Tell Donald to do something."));
      return;
    }
    for (const a of actions) {
      const row = el("div", "act " + (a.ok ? "ok" : a.needs_confirmation ? "wait" : "fail"));
      row.append(el("span", "act-icon", actionIcon(a)));
      const body = el("div", "act-body");
      const head = el("div", "act-head");
      head.append(el("span", "act-name", a.action), el("span", "act-time", ago(a.ts)));
      body.append(head, el("div", "act-sum", a.summary || ""));
      if (a.detail) body.append(el("code", "act-detail", a.detail));
      if (a.transcript) body.append(el("div", "act-src", `“${a.transcript}”`));
      row.append(body);
      feed.append(row);
    }
  }

  function renderReminders(items) {
    const box = $("reminders");
    box.innerHTML = "";
    if (!items.length) {
      box.append(el("p", "empty", "Nothing scheduled."));
      return;
    }
    for (const r of items) {
      const row = el("div", "rem");
      const secs = Math.round(r.in_seconds);
      const when = secs >= 60 ? `${Math.round(secs / 60)}m` : `${secs}s`;
      row.append(el("span", "rem-when", when), el("span", "rem-msg", r.message));
      box.append(row);
    }
  }

  function renderFacts(facts) {
    const ul = $("facts");
    ul.innerHTML = "";
    if (!facts.length) {
      ul.append(el("li", "empty", 'No facts yet. Say "remember that…".'));
      return;
    }
    facts.forEach((f) => ul.append(el("li", null, f)));
  }

  function renderContext(ctx) {
    const box = $("context");
    box.innerHTML = "";
    const rows = [
      ["Time", ctx.time],
      ["Machine", ctx.platform],
      ["Foreground app", ctx.active_app],
    ];
    for (const [k, v] of rows) {
      if (!v) continue;
      const r = el("div", "ctx-row");
      r.append(el("span", "ctx-k", k), el("span", "ctx-v", v));
      box.append(r);
    }
    if (!box.children.length) box.append(el("p", "empty", "No context available."));
  }

  function renderConvo(turns) {
    const box = $("convo");
    box.innerHTML = "";
    if (!turns.length) {
      box.append(el("p", "empty", "Nothing yet."));
      return;
    }
    for (const t of turns) {
      const b = el("div", "cv " + (t.role === "user" ? "cv-you" : "cv-donald"));
      b.append(el("span", "cv-role", t.role === "user" ? "You" : "Donald"), el("span", "cv-text", t.content));
      box.append(b);
    }
    box.scrollTop = box.scrollHeight;
  }

  async function refresh() {
    try {
      const d = await (await fetch("/api/dashboard")).json();
      renderStatus(d.status);
      $("stat-turns").textContent = d.stats.turns;
      $("stat-actions").textContent = d.stats.actions;
      $("stat-reminders").textContent = d.stats.reminders_pending;
      $("stat-facts").textContent = d.stats.facts;
      renderFeed(d.actions);
      renderReminders(d.reminders);
      renderFacts(d.memory.facts);
      renderContext(d.context);
      renderConvo(d.memory.recent_turns);
      $("conn").textContent = "live · updated " + new Date().toLocaleTimeString();
      $("conn").className = "conn ok";
    } catch (e) {
      $("conn").textContent = "disconnected — is the server running?";
      $("conn").className = "conn bad";
    }
  }

  $("kill").addEventListener("click", async () => {
    try {
      await fetch("/api/killswitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: paused ? "release" : "engage" }),
      });
    } catch (_) {}
    refresh();
  });

  refresh();
  setInterval(refresh, 2000);
})();
