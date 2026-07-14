"use strict";
// Donald OS web shell — a dashboard over the combined server (auth + gateway +
// memory + OAuth). No build step, no external deps, CSP-safe.

const TOKEN_KEY = "donald.token";
const $ = (id) => document.getElementById(id);
const api = (path, opts = {}) => {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) headers["Authorization"] = "Bearer " + t;
  return fetch(path, { ...opts, headers });
};

let mode = "login", ws = null;

/* ── auth ─────────────────────────────────────────────────────────────── */
function setMode(m) {
  mode = m;
  $("tab-login").classList.toggle("active", m === "login");
  $("tab-signup").classList.toggle("active", m === "signup");
  document.querySelector(".signup-only").classList.toggle("hidden", m !== "signup");
  $("auth-submit").textContent = m === "login" ? "Log in" : "Create account";
  $("auth-error").classList.add("hidden");
}
async function submitAuth(ev) {
  ev.preventDefault();
  const body = { email: $("f-email").value.trim(), password: $("f-password").value };
  if (mode === "signup") {
    body.display_name = $("f-name").value.trim();
    body.country = $("f-country").value.trim() || null;
    body.dob = $("f-dob").value || null;
    body.accept_tos = $("f-tos").checked;
    if (!body.accept_tos) return showError("Please accept the Terms of Service.");
  }
  try {
    const r = await api(mode === "login" ? "/auth/login" : "/auth/signup",
      { method: "POST", body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) return showError(data.detail || "Something went wrong.");
    localStorage.setItem(TOKEN_KEY, data.token);
    enterApp();
  } catch { showError("Network error — is the server running?"); }
}
function showError(m) { const e = $("auth-error"); e.textContent = m; e.classList.remove("hidden"); }
function show(view) {
  $("auth").classList.toggle("hidden", view !== "auth");
  $("app").classList.toggle("hidden", view !== "app");
}
async function boot() {
  if (!localStorage.getItem(TOKEN_KEY)) return show("auth");
  const r = await api("/auth/me");
  if (r.ok) enterApp(); else { localStorage.removeItem(TOKEN_KEY); show("auth"); }
}
function enterApp() {
  show("app");
  renderCalendar(new Date());
  loadRuns(); loadProviders(); loadBilling(); connectWs();
  startOrb(); startStarfield(); startClock();
}

/* ── clock ────────────────────────────────────────────────────────────── */
function startClock() {
  const tick = () => {
    const d = new Date();
    $("clock").textContent = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
  };
  tick(); setInterval(tick, 1000);
}

/* ── calendar ─────────────────────────────────────────────────────────── */
let calDate = new Date();
function renderCalendar(base) {
  calDate = new Date(base.getFullYear(), base.getMonth(), 1);
  const today = new Date();
  const y = calDate.getFullYear(), m = calDate.getMonth();
  $("cal-title").textContent = calDate.toLocaleString("en-US", { month: "long", year: "numeric" }).toUpperCase();
  const grid = $("cal-grid"); grid.innerHTML = "";
  for (const d of ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]) {
    const el = document.createElement("div"); el.className = "dow"; el.textContent = d; grid.appendChild(el);
  }
  const first = new Date(y, m, 1).getDay(), days = new Date(y, m + 1, 0).getDate();
  for (let i = 0; i < first; i++) grid.appendChild(document.createElement("div"));
  for (let day = 1; day <= days; day++) {
    const el = document.createElement("div"); el.className = "day"; el.textContent = day;
    if (day === today.getDate() && m === today.getMonth() && y === today.getFullYear()) el.classList.add("today");
    if (day % 5 === 0 || day % 7 === 0) { const p = document.createElement("span"); p.className = "pip"; el.appendChild(p); }
    grid.appendChild(el);
  }
}

/* ── runs -> stats / agenda / docs ────────────────────────────────────── */
async function loadRuns() {
  try {
    const { runs } = await (await api("/runs")).json();
    const active = runs.filter(r => r.status === "running").length;
    $("stat-active").textContent = active;
    $("stat-done").textContent = runs.filter(r => r.status === "done").length;
    $("idle-note").textContent = active ? `${active} companion${active > 1 ? "s" : ""} working` : "All companions idle";

    const agenda = $("agenda");
    const recent = runs.slice(0, 4);
    agenda.innerHTML = recent.length ? "" : '<li class="muted">No activity yet</li>';
    for (const r of recent) {
      const li = document.createElement("li");
      const t = document.createElement("span"); t.className = "tick";
      const b = document.createElement("div"); b.className = "a-body";
      b.innerHTML = `<b>${escapeHtml(clip(r.summary || "Session", 42))}</b><span class="a-time">${fmtTime(r.started_at)}</span>`;
      li.append(t, b); agenda.appendChild(li);
    }

    const docs = $("docs");
    docs.innerHTML = runs.length ? "" : '<li class="muted">No documents yet</li>';
    for (const r of runs.slice(0, 10)) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="fico">▤</span><span class="dtext">${escapeHtml(clip(r.summary || "Untitled session", 60))}</span>`;
      docs.appendChild(li);
    }
  } catch { /* leave placeholders */ }
}

/* ── OAuth integrations ───────────────────────────────────────────────── */
async function loadProviders() {
  const list = $("integrations");
  try {
    const { providers } = await (await api("/oauth/providers")).json();
    list.innerHTML = "";
    for (const p of providers) {
      const li = document.createElement("li");
      const name = document.createElement("span"); name.textContent = cap(p.name);
      li.appendChild(name);
      if (p.connected) {
        const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = "● connected";
        li.appendChild(badge);
      } else {
        const btn = document.createElement("button");
        btn.textContent = p.configured ? "Connect" : "Not configured";
        btn.disabled = !p.configured;
        if (p.configured) btn.onclick = () => connectProvider(p.name);
        li.appendChild(btn);
      }
      list.appendChild(li);
    }
  } catch { list.innerHTML = '<li class="muted">Unavailable</li>'; }
}
async function connectProvider(name) {
  const r = await api(`/oauth/${name}/authorize`);
  if (r.ok) { const { authorize_url } = await r.json(); window.open(authorize_url, "_blank"); }
}

/* ── billing (plan pill) ──────────────────────────────────────────────── */
async function loadBilling() {
  const pill = $("plan");
  try {
    const s = await (await api("/billing/subscription")).json();
    pill.classList.remove("hidden", "pro", "upgrade");
    if (s.plan === "pro") { pill.textContent = "PRO"; pill.classList.add("pro"); pill.onclick = openPortal; }
    else if (s.configured) { pill.textContent = "UPGRADE"; pill.classList.add("upgrade"); pill.onclick = startCheckout; }
    else { pill.textContent = "FREE"; pill.onclick = null; }
  } catch { pill.classList.add("hidden"); }
}
async function startCheckout() {
  const r = await api("/billing/checkout", { method: "POST" });
  if (r.ok) location.href = (await r.json()).url;
}
async function openPortal() {
  const r = await api("/billing/portal", { method: "POST" });
  if (r.ok) location.href = (await r.json()).url;
}

/* ── chat (tabbed personas over one WS) ───────────────────────────────── */
const histories = {}; let persona = "donald", awaiting = null, streamEl = null;
function connectWs() {
  const t = localStorage.getItem(TOKEN_KEY);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(t)}`);
  const dot = $("conn-dot");
  ws.onopen = () => dot.classList.add("live");
  ws.onclose = () => dot.classList.remove("live");
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
}
function hist(p) { return (histories[p] = histories[p] || []); }
function renderMessages() {
  const box = $("messages"); box.innerHTML = "";
  for (const m of hist(persona)) {
    const el = document.createElement("div"); el.className = "msg " + m.kind; el.textContent = m.text;
    box.appendChild(el);
  }
  box.scrollTop = box.scrollHeight;
}
function handleEvent(e) {
  const target = awaiting || persona;
  const h = hist(target);
  if (e.type === "delta") {
    if (!streamEl) { streamEl = { kind: "donald", text: "" }; h.push(streamEl); }
    streamEl.text += e.text;
  } else if (e.type === "final") {
    if (!streamEl && e.text) h.push({ kind: "donald", text: e.text });
    streamEl = null; awaiting = null;
  } else if (e.type === "error") {
    h.push({ kind: "error", text: friendlyError(e.text) }); streamEl = null; awaiting = null;
  }
  if (target === persona) renderMessages();
  if (e.type === "final" || e.type === "error") loadRuns();  // refresh stats/agenda
}
function friendlyError(text) {
  const t = String(text || "");
  if (/401|invalid x-api-key|authentication_error|api key/i.test(t))
    return "⚠ Donald's model isn't configured yet — set ANTHROPIC_API_KEY on the server.";
  if (/rate|429/i.test(t)) return "⚠ Rate limited — give it a moment and try again.";
  return "⚠ " + t.slice(0, 160);
}
function sendChat(ev) {
  ev.preventDefault();
  const input = $("chat-input"); const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  hist(persona).push({ kind: "user", text });
  streamEl = null; awaiting = persona;
  renderMessages();
  ws.send(JSON.stringify({ type: "chat", session_id: persona, message: text }));
  input.value = "";
}
function switchPersona(p) {
  persona = p;
  document.querySelectorAll(".ctab").forEach(t => t.classList.toggle("active", t.dataset.persona === p));
  $("chat-input").placeholder = `Message ${cap(p)}…`;
  renderMessages();
}

/* ── orb (rotating dot sphere) ────────────────────────────────────────── */
function startOrb() {
  const canvas = $("orb"), ctx = canvas.getContext("2d");
  const N = 720, pts = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y);
    const th = i * 2.399963; // golden angle
    pts.push([Math.cos(th) * r, y, Math.sin(th) * r]);
  }
  let a = 0;
  function size() {
    const dpr = Math.min(devicePixelRatio || 1, 2), b = canvas.getBoundingClientRect();
    canvas.width = b.width * dpr; canvas.height = b.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return b;
  }
  let box = size();
  window.addEventListener("resize", () => { box = size(); });
  (function frame() {
    if ($("app").classList.contains("hidden")) return requestAnimationFrame(frame);
    a += 0.0016;
    ctx.clearRect(0, 0, box.width, box.height);
    const cx = box.width / 2, cy = box.height / 2, R = Math.min(box.width, box.height) * 0.34;
    const sa = Math.sin(a), ca = Math.cos(a), tilt = 0.42, st = Math.sin(tilt), ct = Math.cos(tilt);
    for (const p of pts) {
      let x = p[0] * ca - p[2] * sa, z = p[0] * sa + p[2] * ca, y = p[1];
      const y2 = y * ct - z * st, z2 = y * st + z * ct;
      const depth = (z2 + 1) / 2; // 0 back .. 1 front
      const sx = cx + x * R, sy = cy + y2 * R;
      ctx.globalAlpha = 0.15 + depth * 0.85;
      ctx.fillStyle = `rgb(${40 + depth * 30},${180 + depth * 40},${175 + depth * 30})`;
      const rad = 0.6 + depth * 1.9;
      ctx.beginPath(); ctx.arc(sx, sy, rad, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  })();
}

/* ── starfield ────────────────────────────────────────────────────────── */
function startStarfield() {
  const c = $("starfield"), ctx = c.getContext("2d");
  let stars = [];
  function resize() {
    c.width = innerWidth; c.height = innerHeight;
    stars = Array.from({ length: 130 }, () => ({
      x: Math.random() * c.width, y: Math.random() * c.height,
      r: Math.random() * 1.3 + 0.2, t: Math.random() * 6.28,
      tint: Math.random() < 0.5 ? "245,115,43" : "55,202,187",
    }));
  }
  resize(); window.addEventListener("resize", resize);
  (function frame() {
    ctx.clearRect(0, 0, c.width, c.height);
    for (const s of stars) {
      s.t += 0.01; const a = 0.12 + (Math.sin(s.t) + 1) * 0.14;
      ctx.globalAlpha = a; ctx.fillStyle = `rgb(${s.tint})`;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1; requestAnimationFrame(frame);
  })();
}

/* ── helpers ──────────────────────────────────────────────────────────── */
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const clip = (s, n) => (s || "").length > n ? s.slice(0, n - 1) + "…" : (s || "");
const escapeHtml = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fmtTime(iso) { try { return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }); } catch { return ""; } }
function logout() {
  api("/auth/logout", { method: "POST" }).finally(() => {
    localStorage.removeItem(TOKEN_KEY); if (ws) ws.close(); show("auth");
  });
}

/* ── wire up ──────────────────────────────────────────────────────────── */
$("tab-login").onclick = () => setMode("login");
$("tab-signup").onclick = () => setMode("signup");
$("auth-form").onsubmit = submitAuth;
$("chat-form").onsubmit = sendChat;
$("logout").onclick = logout;
$("cal-prev").onclick = () => renderCalendar(new Date(calDate.getFullYear(), calDate.getMonth() - 1, 1));
$("cal-next").onclick = () => renderCalendar(new Date(calDate.getFullYear(), calDate.getMonth() + 1, 1));
document.querySelectorAll(".ctab").forEach(t => t.onclick = () => switchPersona(t.dataset.persona));
setMode("login");
boot();
