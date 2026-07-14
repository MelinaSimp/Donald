"use strict";
// Donald web shell — talks to the combined server (backend auth + gateway chat).
// No build step, no external deps: served as static files from /app.

const TOKEN_KEY = "donald.token";
const $ = (id) => document.getElementById(id);
const api = (path, opts = {}) => {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = "Bearer " + token;
  return fetch(path, { ...opts, headers });
};

let ws = null;
let mode = "login"; // or "signup"

// ── auth view ────────────────────────────────────────────────────────────────
function setMode(next) {
  mode = next;
  $("tab-login").classList.toggle("active", mode === "login");
  $("tab-signup").classList.toggle("active", mode === "signup");
  document.querySelector(".signup-only").classList.toggle("hidden", mode !== "signup");
  $("auth-submit").textContent = mode === "login" ? "Log in" : "Create account";
  hideError();
}
function showError(msg) { const e = $("auth-error"); e.textContent = msg; e.classList.remove("hidden"); }
function hideError() { $("auth-error").classList.add("hidden"); }

async function submitAuth(ev) {
  ev.preventDefault();
  hideError();
  const email = $("f-email").value.trim();
  const password = $("f-password").value;
  const path = mode === "login" ? "/auth/login" : "/auth/signup";
  const body = { email, password };
  if (mode === "signup") {
    body.display_name = $("f-name").value.trim();
    body.country = $("f-country").value.trim() || null;
    body.dob = $("f-dob").value || null;
    body.accept_tos = $("f-tos").checked;
    if (!body.accept_tos) return showError("Please accept the Terms of Service.");
  }
  try {
    const r = await api(path, { method: "POST", body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) return showError(data.detail || "Something went wrong.");
    localStorage.setItem(TOKEN_KEY, data.token);
    enterApp(data.user);
  } catch (e) { showError("Network error — is the server running?"); }
}

// ── app view ─────────────────────────────────────────────────────────────────
function show(view) {
  $("auth").classList.toggle("hidden", view !== "auth");
  $("app").classList.toggle("hidden", view !== "app");
}

async function boot() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return show("auth");
  const r = await api("/auth/me");
  if (r.ok) enterApp(await r.json());
  else { localStorage.removeItem(TOKEN_KEY); show("auth"); }
}

function enterApp(user) {
  show("app");
  $("who").textContent = user.email;
  loadIntegrations();
  connectWs();
}

async function loadIntegrations() {
  const list = $("integrations");
  try {
    const r = await api("/integrations");
    const { providers } = await r.json();
    if (!providers.length) { list.innerHTML = '<li class="muted">None connected yet</li>'; return; }
    list.innerHTML = "";
    for (const p of providers) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.innerHTML = '<span class="dot"></span>' + p;
      const rm = document.createElement("button");
      rm.className = "link"; rm.textContent = "Disconnect";
      rm.onclick = async () => { await api("/integrations/" + p, { method: "DELETE" }); loadIntegrations(); };
      li.append(name, rm);
      list.appendChild(li);
    }
  } catch { list.innerHTML = '<li class="muted">Unavailable</li>'; }
}

// ── chat over WebSocket ──────────────────────────────────────────────────────
function connectWs() {
  const token = localStorage.getItem(TOKEN_KEY);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);
  const conn = $("conn");
  ws.onopen = () => { conn.textContent = "● connected"; conn.classList.add("live"); };
  ws.onclose = () => { conn.textContent = "○ disconnected"; conn.classList.remove("live"); };
  ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
}

let streamingEl = null;
function handleEvent(e) {
  if (e.type === "delta") {
    if (!streamingEl) streamingEl = addMessage("donald", "");
    streamingEl.textContent += e.text;
    scrollDown();
  } else if (e.type === "final") {
    if (!streamingEl && e.text) addMessage("donald", e.text);
    streamingEl = null;
  } else if (e.type === "error") {
    addMessage("error", e.text || "error");
    streamingEl = null;
  }
}

function sendChat(ev) {
  ev.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  addMessage("user", text);
  streamingEl = null;
  ws.send(JSON.stringify({ type: "chat", session_id: "web", message: text }));
  input.value = "";
}

function addMessage(kind, text) {
  const el = document.createElement("div");
  el.className = "msg " + kind;
  el.textContent = text;
  $("messages").appendChild(el);
  scrollDown();
  return el;
}
function scrollDown() { const m = $("messages"); m.scrollTop = m.scrollHeight; }

function logout() {
  api("/auth/logout", { method: "POST" }).finally(() => {
    localStorage.removeItem(TOKEN_KEY);
    if (ws) ws.close();
    show("auth");
  });
}

// ── wire up ──────────────────────────────────────────────────────────────────
$("tab-login").onclick = () => setMode("login");
$("tab-signup").onclick = () => setMode("signup");
$("auth-form").onsubmit = submitAuth;
$("chat-form").onsubmit = sendChat;
$("logout").onclick = logout;
setMode("login");
boot();
