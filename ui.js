// ============================================================
// Trillion UI glue
//  - mic toggle (idle <-> listening) + trillion:mic-toggle event
//  - status indicator states (idle / listening / processing)
//  - activity panel collapse
//  - floating response cards
//  - live mic amplitude -> orb uVoiceBright (with graceful fallback)
// ============================================================
(function () {
  "use strict";

  const body = document.body;
  const mic = document.getElementById("mic");
  const micHint = document.getElementById("micHint");
  const statusLabel = document.getElementById("statusLabel");
  const panel = document.getElementById("panel");
  const panelToggle = document.getElementById("panelToggle");
  const cardsRoot = document.getElementById("cards");

  let listening = false;

  // ----------------------------------------------------------
  // Status helper
  // ----------------------------------------------------------
  const LABELS = { idle: "Idle", listening: "Listening", processing: "Processing" };
  function setState(state) {
    body.dataset.state = state;
    statusLabel.textContent = LABELS[state] || "Idle";
  }
  setState("idle");

  // ----------------------------------------------------------
  // Activity panel collapse
  // ----------------------------------------------------------
  panelToggle.addEventListener("click", () => {
    panel.classList.toggle("is-collapsed");
    const collapsed = panel.classList.contains("is-collapsed");
    panelToggle.setAttribute("aria-label", collapsed ? "Expand panel" : "Collapse panel");
  });

  // ----------------------------------------------------------
  // Floating response cards (demo content)
  // ----------------------------------------------------------
  const CARD_DATA = [
    {
      cls: "card--revenue",
      label: "Revenue · This week",
      kind: "big",
      big: "$48.2k",
      delta: "▲ 12.4% vs last week",
      pos: { left: "10%", top: "26%" },
    },
    {
      label: "Inbox",
      title: "Maya replied",
      body: "“Looks great — let's lock the Q3 partnership terms by Friday.”",
      pos: { left: "13%", top: "58%" },
    },
    {
      label: "Scout · Done",
      title: "Competitor scan",
      body: "3 new pricing changes detected across tracked rivals.",
      pos: { right: "23%", top: "30%" },
    },
  ];

  function buildCard(d, i) {
    const el = document.createElement("div");
    el.className = "card" + (d.cls ? " " + d.cls : "");
    el.style.animationDelay = `${i * 140}ms, ${550 + i * 140}ms`;
    Object.assign(el.style, d.pos);

    let inner = `<div class="card__label">${d.label}</div>`;
    if (d.kind === "big") {
      inner += `<div class="card__big">${d.big}</div><div class="card__delta">${d.delta}</div>`;
    } else {
      inner += `<div class="card__title">${d.title}</div><div class="card__body">${d.body}</div>`;
    }
    el.innerHTML = inner;
    return el;
  }

  function showCards() {
    if (cardsRoot.childElementCount) return;
    CARD_DATA.forEach((d, i) => cardsRoot.appendChild(buildCard(d, i)));
  }
  function clearCards() {
    cardsRoot.innerHTML = "";
  }

  // Surface a couple of cards shortly after load so the scene feels alive.
  setTimeout(showCards, 900);

  // ----------------------------------------------------------
  // Live microphone -> orb brightness
  // ----------------------------------------------------------
  let audioCtx = null;
  let analyser = null;
  let micStream = null;
  let rafId = null;
  let fakeDriver = null;
  const ampData = new Uint8Array(64);

  function driveFromAnalyser() {
    analyser.getByteTimeDomainData(ampData);
    let sum = 0;
    for (let i = 0; i < ampData.length; i++) {
      const v = (ampData[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / ampData.length);
    // map RMS -> 0..1 with a little gain
    const bright = Math.min(1, rms * 4.5);
    if (window.trillionScene) window.trillionScene.setVoiceBright(bright);
    rafId = requestAnimationFrame(driveFromAnalyser);
  }

  async function startMicAudio() {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(micStream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      src.connect(analyser);
      driveFromAnalyser();
      return true;
    } catch (err) {
      // No mic / denied permission -> fall back to a synthetic shimmer
      // so the orb still reacts and the demo stays self-contained.
      console.info("[Trillion] mic unavailable, using synthetic voice driver:", err && err.name);
      let phase = 0;
      fakeDriver = setInterval(() => {
        phase += 0.18;
        const b = 0.35 + 0.35 * Math.abs(Math.sin(phase)) + Math.random() * 0.15;
        if (window.trillionScene) window.trillionScene.setVoiceBright(Math.min(1, b));
      }, 60);
      return false;
    }
  }

  function stopMicAudio() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    if (fakeDriver) clearInterval(fakeDriver);
    fakeDriver = null;
    if (micStream) micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
    if (audioCtx) audioCtx.close().catch(() => {});
    audioCtx = null;
    analyser = null;
    if (window.trillionScene) window.trillionScene.setVoiceBright(0);
  }

  // ----------------------------------------------------------
  // Mic button toggle
  // ----------------------------------------------------------
  let processingTimer = null;

  async function toggleMic() {
    listening = !listening;
    mic.classList.toggle("is-listening", listening);
    mic.setAttribute("aria-pressed", String(listening));

    // Notify the rest of the app.
    window.dispatchEvent(
      new CustomEvent("trillion:mic-toggle", { detail: { listening } })
    );

    if (listening) {
      clearTimeout(processingTimer);
      setState("listening");
      await startMicAudio();
    } else {
      stopMicAudio();
      // Simulate the assistant thinking, then returning to idle.
      setState("processing");
      processingTimer = setTimeout(() => {
        setState("idle");
        showCards();
      }, 1600);
    }
  }

  mic.addEventListener("click", toggleMic);

  // Spacebar as a quick push-to-talk style toggle.
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space" && e.target === document.body) {
      e.preventDefault();
      toggleMic();
    }
  });

  // Example of another part of the app reacting to the event.
  window.addEventListener("trillion:mic-toggle", (e) => {
    micHint.textContent = e.detail.listening
      ? "Listening… tap to stop"
      : 'Tap or say "Hey Trillion"';
  });
})();
