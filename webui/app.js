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

let mode = "login", ws = null, ORB = null;

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
  loadRuns(); loadProviders(); loadBilling(); loadMemory(); connectWs();
  ORB = startOrb(); startStarfield(); startClock();
  setInterval(() => {
    if (!ORB) return; const n = ORB.activeCount();
    $("stat-active").textContent = n;
    $("idle-note").textContent = n ? `${n} companion${n > 1 ? "s" : ""} working…` : "All companions idle";
  }, 350);
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

/* ── memory panel ─────────────────────────────────────────────────────── */
async function loadMemory() {
  const list = $("memory");
  try {
    const { facts } = await (await api("/memory")).json();
    if (!facts.length) { list.innerHTML = '<li class="muted">Tell Donald something about you →</li>'; return; }
    list.innerHTML = "";
    for (const f of facts) {
      const li = document.createElement("li");
      const tick = document.createElement("span"); tick.className = "tick";
      const txt = document.createElement("span"); txt.className = "mtext"; txt.textContent = f.content;
      const del = document.createElement("button"); del.className = "mdel"; del.title = "Forget this"; del.textContent = "✕";
      del.onclick = async () => { await api("/memory/" + f.id, { method: "DELETE" }); loadMemory(); };
      li.append(tick, txt, del);
      list.appendChild(li);
    }
  } catch { /* leave placeholder */ }
}

/* ── voice (browser speech; server Deepgram/ElevenLabs is the HQ path) ─── */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null, listening = false, speakNext = false;
function toggleVoice() {
  if (!SR) return toast("Voice input isn't supported in this browser.");
  if (listening) { recog.stop(); return; }
  recog = new SR(); recog.lang = "en-US"; recog.interimResults = false; recog.maxAlternatives = 1;
  recog.onstart = () => { listening = true; $("voice").classList.add("listening"); };
  recog.onend = () => { listening = false; $("voice").classList.remove("listening"); };
  recog.onerror = () => toast("Didn't catch that — try again.");
  recog.onresult = (e) => {
    const text = e.results[0][0].transcript;
    $("chat-input").value = text; speakNext = true; sendChat(new Event("submit"));
  };
  recog.start();
}
function speak(text) {
  if (!window.speechSynthesis || !text) return;
  const u = new SpeechSynthesisUtterance(text.slice(0, 600));
  u.rate = 1.05; u.pitch = 1;
  window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
}
function toast(msg) {
  const el = document.createElement("div"); el.textContent = msg; el.className = "toast";
  el.style.cssText = "position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#141821;border:1px solid var(--line);color:var(--text);padding:10px 18px;border-radius:10px;z-index:9;font-size:13px";
  document.body.appendChild(el); setTimeout(() => el.remove(), 2400);
}

/* ── confirmation-gated action (create a GitHub issue) ────────────────── */
function openIssueModal() {
  $("confirm-overlay").classList.remove("hidden");
  $("confirm-preview").classList.add("hidden");
  $("confirm-result").classList.add("hidden");
  $("confirm-approve").classList.add("hidden");
  $("confirm-preview-btn").classList.remove("hidden");
  $("issue-repo").value = ""; $("issue-title").value = "";
}
function closeIssueModal() { $("confirm-overlay").classList.add("hidden"); }
async function issuePreview() {
  const repo = $("issue-repo").value.trim(), title = $("issue-title").value.trim();
  if (!repo || !title) return toast("Enter a repo (owner/name) and a title.");
  const r = await api("/integrations/github/issue", { method: "POST", body: JSON.stringify({ repo, title }) });
  const data = await r.json();
  if (!r.ok) return showConfirmResult(data.detail || "Couldn't preview.", false);
  const pv = $("confirm-preview");
  pv.textContent = "Donald will: " + data.preview.summary; pv.classList.remove("hidden");
  $("confirm-preview-btn").classList.add("hidden");
  $("confirm-approve").classList.remove("hidden");
}
async function issueApprove() {
  const repo = $("issue-repo").value.trim(), title = $("issue-title").value.trim();
  const r = await api("/integrations/github/issue", { method: "POST", body: JSON.stringify({ repo, title, confirm: true }) });
  const data = await r.json();
  if (!r.ok) return showConfirmResult(data.detail || "Failed.", false);
  showConfirmResult("Created: " + (data.url || "issue #" + data.number), true);
}
function showConfirmResult(text, ok) {
  const el = $("confirm-result"); el.textContent = text;
  el.className = "confirm-result " + (ok ? "ok" : "err"); el.classList.remove("hidden");
  $("confirm-approve").classList.add("hidden"); $("confirm-preview-btn").classList.add("hidden");
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
    if (ORB) ORB.speak();  // Donald pulses while it talks
    if (!streamEl) { streamEl = { kind: "donald", text: "" }; h.push(streamEl); }
    streamEl.text += e.text;
  } else if (e.type === "final") {
    if (!streamEl && e.text) h.push({ kind: "donald", text: e.text });
    streamEl = null; awaiting = null;
  } else if (e.type === "error") {
    h.push({ kind: "error", text: friendlyError(e.text) }); streamEl = null; awaiting = null;
  }
  if (target === persona) renderMessages();
  if (e.type === "final" || e.type === "error") { loadRuns(); loadMemory(); }
  if (e.type === "final" && speakNext) { speak(e.text); speakNext = false; }
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
  if (ORB) { ORB.think(); ORB.dispatch(chooseAgent(text)); }  // hand the task to a sub-agent
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

/* ── orb system: Donald + orbiting sub-agents ────────────────────────── */
const AGENTS = [
  { key: "engineer", label: "ENGINEER", hue: 205 },
  { key: "finance",  label: "FINANCE",  hue: 158 },
  { key: "marketer", label: "MARKETER", hue: 190 },
  { key: "research", label: "RESEARCH", hue: 222 },
];
function sphere(n) { const p = []; for (let i = 0; i < n; i++) { const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = i * 2.399963; p.push([Math.cos(th) * r, y, Math.sin(th) * r]); } return p; }
function chooseAgent(text) {
  if (persona !== "donald" && AGENTS.some(a => a.key === persona)) return persona;
  const t = (text || "").toLowerCase();
  if (/\b(code|bug|deploy|repo|api|build|test|error)\b/.test(t)) return "engineer";
  if (/\b(budget|invoice|revenue|cost|price|finance|runway|expense)\b/.test(t)) return "finance";
  if (/\b(campaign|copy|launch|market|brand|ad|post|content|audience)\b/.test(t)) return "marketer";
  return "research";
}
function startOrb() {
  const canvas = $("orb"), ctx = canvas.getContext("2d");
  const mainPts = sphere(760), subPts = sphere(150);
  const subs = AGENTS.map(a => ({ ...a, activity: 0, phase: Math.random() * 6.28 }));
  let a = 0, box, speaking = 0, thinking = 0, particles = [];
  function size() { const dpr = Math.min(devicePixelRatio || 1, 2), b = canvas.getBoundingClientRect(); canvas.width = b.width * dpr; canvas.height = b.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); box = b; }
  size(); window.addEventListener("resize", size);
  function subPos(i, cx, cy, R) {
    const n = subs.length, ang = -Math.PI / 2 + (i + 0.5) / n * Math.PI * 2;
    const rx = Math.min(box.width * 0.40, R * 2.5), ry = box.height * 0.33;
    return { x: cx + Math.cos(ang) * rx, y: cy + Math.sin(ang) * ry, r: R * 0.26 };
  }
  function drawOrb(pts, cx, cy, R, hue, bright, rot) {
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.7);
    g.addColorStop(0, `hsla(${hue},75%,55%,${0.08 + bright * 0.20})`); g.addColorStop(1, "hsla(0,0%,0%,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 1.7, 0, 6.2832); ctx.fill();
    const sa = Math.sin(rot), ca = Math.cos(rot), st = Math.sin(0.42), ct = Math.cos(0.42);
    for (const p of pts) {
      const x = p[0] * ca - p[2] * sa, z = p[0] * sa + p[2] * ca, y2 = p[1] * ct - z * st, z2 = p[1] * st + z * ct;
      const depth = (z2 + 1) / 2, sx = cx + x * R, sy = cy + y2 * R;
      ctx.globalAlpha = (0.12 + depth * 0.85) * (0.45 + bright * 0.55);
      ctx.fillStyle = `hsl(${hue}, ${58 + bright * 30}%, ${44 + depth * 26 + bright * 8}%)`;
      ctx.beginPath(); ctx.arc(sx, sy, 0.5 + depth * (1.5 + bright * 1.4), 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  (function frame() {
    requestAnimationFrame(frame);
    if ($("app").classList.contains("hidden")) return;
    a += 0.0016 + thinking * 0.004; speaking *= 0.93; thinking *= 0.97;
    ctx.clearRect(0, 0, box.width, box.height);
    const cx = box.width / 2, cy = box.height / 2, R = Math.min(box.width, box.height) * 0.28;
    subs.forEach((s, i) => {
      s.activity *= 0.986; s.phase += 0.02;
      const pos = subPos(i, cx, cy, R), fx = pos.x + Math.sin(s.phase) * 7, fy = pos.y + Math.cos(s.phase * 0.8) * 7;
      if (s.activity > 0.04) { ctx.strokeStyle = `hsla(${s.hue},75%,58%,${s.activity * 0.4})`; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(fx, fy); ctx.stroke(); }
      drawOrb(subPts, fx, fy, pos.r * (1 + s.activity * 0.28), s.hue, s.activity, a * 1.5 + i);
      ctx.globalAlpha = 0.28 + s.activity * 0.6; ctx.fillStyle = `hsl(${s.hue},65%,72%)`;
      ctx.font = "10px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.fillText(s.label, fx, fy + pos.r + 15); ctx.globalAlpha = 1;
    });
    particles = particles.filter(p => {
      p.t += 0.022; if (p.t >= 1) { subs[p.to].activity = Math.min(1, subs[p.to].activity + 0.9); return false; }
      if (p.t < 0) return true;
      const pos = subPos(p.to, cx, cy, R), mx = (cx + pos.x) / 2, my = (cy + pos.y) / 2 - 42, t = p.t;
      const x = (1 - t) * (1 - t) * cx + 2 * (1 - t) * t * mx + t * t * pos.x;
      const y = (1 - t) * (1 - t) * cy + 2 * (1 - t) * t * my + t * t * pos.y;
      ctx.fillStyle = `hsl(${subs[p.to].hue},85%,62%)`; ctx.globalAlpha = 1 - Math.abs(t - 0.5);
      ctx.beginPath(); ctx.arc(x, y, 2.4, 0, 6.2832); ctx.fill(); ctx.globalAlpha = 1; return true;
    });
    const pulse = 1 + speaking * 0.15 + Math.sin(a * 3) * 0.014;
    drawOrb(mainPts, cx + Math.sin(a * 0.7) * 5, cy + Math.cos(a * 0.9) * 5, R * pulse, 184, 0.52 + speaking * 0.48, a);
  })();
  return {
    speak() { speaking = 1; }, think() { thinking = 1; },
    dispatch(key) { const i = subs.findIndex(s => s.key === key); if (i < 0) return; thinking = 1; for (let k = 0; k < 4; k++) particles.push({ to: i, t: -k * 0.10 }); },
    activeCount() { return subs.filter(s => s.activity > 0.12).length; },
  };
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
$("voice").onclick = toggleVoice;
$("btn-insert").onclick = openIssueModal;
$("btn-upload").onclick = () => toast("File upload is coming soon.");
$("confirm-cancel").onclick = closeIssueModal;
$("confirm-preview-btn").onclick = issuePreview;
$("confirm-approve").onclick = issueApprove;
$("cal-prev").onclick = () => renderCalendar(new Date(calDate.getFullYear(), calDate.getMonth() - 1, 1));
$("cal-next").onclick = () => renderCalendar(new Date(calDate.getFullYear(), calDate.getMonth() + 1, 1));
document.querySelectorAll(".ctab").forEach(t => t.onclick = () => switchPersona(t.dataset.persona));
setMode("login");
boot();
