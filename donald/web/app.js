// Donald — front-end voice loop.
//
// The browser is the ears and the mouth: the Web Speech API handles wake-word
// detection, speech-to-text, and Donald's spoken voice. The Python server is
// the brain + hands. One spoken command = one POST to /api/turn.

(() => {
  "use strict";

  const WAKE_WORD = "donald";
  // Kept in sync with donald/killswitch.py — caught locally so "stop" never
  // has to wait on the model or the network round-trip.
  const STOP_PHRASES = ["stop", "freeze", "kill switch", "halt", "abort", "shut it down"];
  const RESUME_PHRASES = ["resume", "wake up", "you're back", "unfreeze", "carry on", "go ahead"];

  const orb = document.getElementById("orb");
  const statusEl = document.getElementById("status");
  const transcriptEl = document.getElementById("transcript");
  const startBtn = document.getElementById("start");
  const pttBtn = document.getElementById("ptt");
  const killBtn = document.getElementById("kill");
  const muteBox = document.getElementById("mute");
  const hintEl = document.getElementById("hint");
  let paused = false;

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    statusEl.innerHTML =
      "This browser has no Web Speech API. Use <b>Chrome</b> or <b>Edge</b> for voice " +
      "(or type to Donald in those).";
    startBtn.disabled = true;
    pttBtn.disabled = true;
    return;
  }

  // mode: "off" | "wake" (waiting to hear "Donald") | "command" (capturing an instruction)
  let mode = "off";
  let active = false; // is the assistant loop running?
  let speaking = false; // is Donald talking? (pause the mic so he doesn't hear himself)
  let busy = false; // is a turn in flight to the server?

  const rec = new SR();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = "en-US";

  function setOrb(state) {
    orb.className = state;
  }

  function addBubble(text, cls) {
    const div = document.createElement("div");
    div.className = `bubble ${cls}`;
    div.textContent = text;
    transcriptEl.appendChild(div);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function speak(text) {
    if (muteBox.checked || !window.speechSynthesis || !text) return;
    speaking = true;
    setOrb("speaking");
    try {
      rec.stop();
    } catch (_) {}
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    u.pitch = 1.0;
    // Prefer a confident, male-ish English voice if one is available.
    const voices = window.speechSynthesis.getVoices();
    const pick = voices.find((v) => /daniel|alex|david|google us english/i.test(v.name));
    if (pick) u.voice = pick;
    u.onend = () => {
      speaking = false;
      if (active) listenAgain();
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  function listenAgain() {
    if (!active || speaking) return;
    try {
      rec.start();
    } catch (_) {
      /* already started */
    }
  }

  async function setKill(engage) {
    try {
      const r = await fetch("/api/killswitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: engage ? "engage" : "release" }),
      });
      paused = (await r.json()).paused;
    } catch (_) {
      paused = engage;
    }
    killBtn.classList.toggle("engaged", paused);
    killBtn.textContent = paused ? "▶ Resume" : "■ Stop";
    orb.classList.toggle("paused", paused);
    if (paused) {
      statusEl.textContent = "Halted. Say “resume” or click Resume.";
      window.speechSynthesis && window.speechSynthesis.cancel();
    } else {
      statusEl.innerHTML = active ? 'Listening for <b>“Donald”</b>…' : "Ready.";
    }
  }

  // Returns true if the utterance was a stop/resume command (already handled).
  function handledAsControl(low) {
    if (STOP_PHRASES.some((p) => low.includes(p))) {
      addBubble("stop", "you");
      setKill(true);
      if (!muteBox.checked) speak("Stopped. I'll be right here.");
      mode = "wake";
      return true;
    }
    if (paused) {
      if (RESUME_PHRASES.some((p) => low.includes(p))) {
        setKill(false);
        if (!muteBox.checked) speak("And we're back. Did you miss me?");
      }
      mode = "wake";
      return true; // while paused, ignore everything except resume
    }
    return false;
  }

  async function sendCommand(text) {
    if (!text) return;
    if (handledAsControl(text.toLowerCase().trim())) return;
    busy = true;
    addBubble(text, "you");
    setOrb("thinking");
    statusEl.textContent = "Donald's working on it…";
    try {
      const res = await fetch("/api/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: text }),
      });
      const data = await res.json();
      (data.actions || []).forEach((a) => {
        const label = `${a.ok ? "✓" : "✕"} ${a.action}: ${a.summary}`;
        addBubble(label, "action" + (a.ok ? "" : " fail"));
      });
      if (data.reply) {
        addBubble(data.reply, "donald");
        speak(data.reply);
      }
    } catch (err) {
      addBubble("Server's not answering. Even I can't fix a dead server with my mouth.", "donald");
    } finally {
      busy = false;
      mode = "wake";
      statusEl.innerHTML = active ? 'Listening for <b>“Donald”</b>…' : "Paused.";
      if (!speaking) {
        setOrb(active ? "listening" : "idle");
        listenAgain();
      }
    }
  }

  // Pull the freshest final transcript out of the results list.
  function latestFinal(event) {
    let out = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) out += event.results[i][0].transcript;
    }
    return out.trim();
  }

  rec.onresult = (event) => {
    if (busy || speaking) return;
    const finalText = latestFinal(event);
    if (!finalText) return;
    const lower = finalText.toLowerCase();

    if (mode === "wake") {
      const idx = lower.indexOf(WAKE_WORD);
      if (idx === -1) return; // ignore chatter until the wake word lands
      const after = finalText.slice(idx + WAKE_WORD.length).replace(/^[\s,.:!?-]+/, "").trim();
      if (after) {
        // "Donald, open Safari" — heard the command in the same breath.
        mode = "command";
        sendCommand(after);
      } else {
        // Just "Donald" — acknowledge and capture the next utterance.
        mode = "command";
        setOrb("listening");
        statusEl.textContent = "Yeah? I'm listening.";
        if (!muteBox.checked) speak("Yeah?");
      }
    } else if (mode === "command") {
      sendCommand(finalText);
    }
  };

  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      statusEl.textContent = "Microphone blocked. Allow it in the address bar, then click Wake Donald.";
      stopLoop();
    }
  };

  rec.onend = () => {
    // The API stops itself periodically; restart while the loop is active.
    if (active && !speaking) listenAgain();
  };

  function startLoop() {
    active = true;
    mode = "wake";
    startBtn.textContent = "Sleep";
    startBtn.classList.add("live");
    statusEl.innerHTML = 'Listening for <b>“Donald”</b>…';
    setOrb("listening");
    if (window.speechSynthesis) window.speechSynthesis.getVoices(); // warm the voice list
    listenAgain();
  }

  function stopLoop() {
    active = false;
    mode = "off";
    startBtn.textContent = "Wake Donald";
    startBtn.classList.remove("live");
    statusEl.textContent = "Paused.";
    setOrb("idle");
    try {
      rec.stop();
    } catch (_) {}
  }

  startBtn.addEventListener("click", () => (active ? stopLoop() : startLoop()));

  // Push-to-talk: hold the button, skip the wake word, talk straight to Donald.
  pttBtn.addEventListener("mousedown", () => {
    if (busy) return;
    active = true;
    mode = "command";
    setOrb("listening");
    statusEl.textContent = "Go ahead…";
    pttBtn.classList.add("live");
    listenAgain();
  });
  const endPtt = () => pttBtn.classList.remove("live");
  pttBtn.addEventListener("mouseup", endPtt);
  pttBtn.addEventListener("mouseleave", endPtt);

  killBtn.addEventListener("click", () => setKill(!paused));

  // Proactivity: Donald can speak first. Poll for lines he wants to say
  // (reminders, alerts) and voice them — this is what makes him feel alive.
  setInterval(async () => {
    try {
      const r = await fetch("/api/events");
      const data = await r.json();
      (data.say || []).forEach((line) => {
        addBubble(line, "donald");
        speak(line);
      });
    } catch (_) {}
  }, 3000);

  // Health check so the user knows the brain is wired up.
  fetch("/api/health")
    .then((r) => r.json())
    .then((h) => {
      if (h.paused) setKill(true);
      if (!h.has_api_key) {
        hintEl.textContent = "⚠ ANTHROPIC_API_KEY isn't set — Donald can hear you but can't think yet.";
      } else {
        hintEl.textContent = `Ready on ${h.platform}. Try: “Donald, remind me in 1 minute to stretch.”`;
      }
    })
    .catch(() => {});

  // Launched by the always-on wake listener (it heard "Donald" and opened us
  // with ?armed=1): skip the button, greet, and start listening for the
  // command right away — so the user just keeps talking.
  if (new URLSearchParams(location.search).has("armed")) {
    active = true;
    mode = "command";
    startBtn.textContent = "Sleep";
    startBtn.classList.add("live");
    setOrb("listening");
    statusEl.textContent = "Yeah? I'm listening.";
    if (window.speechSynthesis) {
      window.speechSynthesis.getVoices();
      // A short greeting both confirms it woke and primes the audio output.
      setTimeout(() => speak("Yeah?"), 250);
    }
    listenAgain();
  }
})();
