import { useState, useEffect, useRef, useCallback } from "react";

// ─── Golden amber palette ───
const GOLD = "#d4a020";
const AMBER = "#e8a832";
const BRIGHT = "#ffcc44";
const HOT = "#fff0b0";
const DEEP = "#8b5e0a";
const DIM_TEXT = "rgba(212,160,32,0.3)";
const MED_TEXT = "rgba(212,160,32,0.55)";
const BG = "#050505";

const STATES = {
  idle: { label: "STANDING BY", energy: 0.4, ringSpeed: 0.3, particles: 120, sparkRate: 0.02 },
  listening: { label: "LISTENING", energy: 0.7, ringSpeed: 0.7, particles: 200, sparkRate: 0.06 },
  thinking: { label: "PROCESSING", energy: 0.9, ringSpeed: 1.2, particles: 300, sparkRate: 0.1 },
  speaking: { label: "SPEAKING", energy: 1.0, ringSpeed: 1.6, particles: 350, sparkRate: 0.14 },
};

function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }
function rand(min: number, max: number) { return min + Math.random() * (max - min); }

export default function DonaldOrb() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number | null>(null);
  const stateRef = useRef("idle");
  const energyRef = useRef({ current: 0.4, target: 0.4 });
  const ringSpeedRef = useRef({ current: 0.3, target: 0.3 });
  const particleCountRef = useRef({ current: 120, target: 120 });
  const sparkRateRef = useRef({ current: 0.02, target: 0.02 });
  const particlesRef = useRef<any[]>([]);
  const sparksRef = useRef<any[]>([]);
  const frameRef = useRef(0);

  const [state, setState] = useState("idle");
  const [statusText, setStatusText] = useState("STANDING BY");
  const [phraseText, setPhraseText] = useState("");
  const [displayedPhrase, setDisplayedPhrase] = useState("");
  const [booted, setBooted] = useState(false);
  const [bootProgress, setBootProgress] = useState(0);

  // Chat wiring
  const sessionIdRef = useRef("web-" + Math.random().toString(36).slice(2));
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  // Voice / clap-to-wake wiring
  const CLAP_THRESHOLD = 0.72;        // 0..1 peak; high so only a loud clap wakes him
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const clapDataRef = useRef<Uint8Array | null>(null);
  const clapRafRef = useRef<number | null>(null);
  const lastClapRef = useRef(0);
  const recognitionRef = useRef<any>(null);
  const awakeRef = useRef(false);       // true = in a live conversation
  const listeningRef = useRef(false);
  const gotSpeechRef = useRef(false);
  const noSpeechRef = useRef(0);
  const [voiceOn, setVoiceOn] = useState(false);
  const [voiceMsg, setVoiceMsg] = useState("");
  // Function holders so send()/startListening() can call each other regardless
  // of definition order.
  const wantListenRef = useRef<() => void>(() => {});
  const sendRef = useRef<(m: string) => void>(() => {});

  // Boot
  useEffect(() => {
    let p = 0;
    const iv = setInterval(() => {
      p += 0.012 + Math.random() * 0.018;
      if (p >= 1) { p = 1; clearInterval(iv); setTimeout(() => setBooted(true), 500); }
      setBootProgress(p);
    }, 40);
    return () => clearInterval(iv);
  }, []);

  // Typing
  useEffect(() => {
    if (!phraseText) { setDisplayedPhrase(""); return; }
    setDisplayedPhrase("");
    let i = 0;
    const iv = setInterval(() => { i++; setDisplayedPhrase(phraseText.slice(0, i)); if (i >= phraseText.length) clearInterval(iv); }, 28);
    return () => clearInterval(iv);
  }, [phraseText]);

  // Transition
  const transitionTo = useCallback((s: string) => {
    stateRef.current = s;
    setState(s);
    setStatusText((STATES as any)[s].label);
    energyRef.current.target = (STATES as any)[s].energy;
    ringSpeedRef.current.target = (STATES as any)[s].ringSpeed;
    particleCountRef.current.target = (STATES as any)[s].particles;
    sparkRateRef.current.target = (STATES as any)[s].sparkRate;
  }, []);

  // Send a message to the Donald gateway (proxied via Next at /gw), show the
  // reply, and play the ElevenLabs voice if the gateway returned one.
  const send = useCallback(async (message: string) => {
    const msg = message.trim();
    if (!msg || stateRef.current === "thinking" || stateRef.current === "speaking") return;
    setInput("");
    setSending(true);
    setPhraseText("");
    transitionTo("thinking");
    try {
      const res = await fetch("/gw/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current, message: msg }),
      });
      const data = await res.json();
      const text: string = (data && data.text) || "…";
      const voiceEv = (data.events || []).find(
        (e: any) => e.type === "voice" && e.audio_b64
      );
      transitionTo("speaking");
      setPhraseText(text);
      // After Donald finishes speaking: go idle, and if we're in a live voice
      // conversation, start listening again for the next thing you say.
      const done = () => {
        transitionTo("idle");
        if (awakeRef.current) { noSpeechRef.current = 0; wantListenRef.current(); }
      };
      if (voiceEv) {
        const audio = new Audio(`data:${voiceEv.mime || "audio/mpeg"};base64,${voiceEv.audio_b64}`);
        audioRef.current = audio;
        audio.onended = done;
        audio.onerror = done;
        audio.play().catch(done);
      } else {
        const dur = Math.min(15000, 2500 + text.length * 45);
        setTimeout(() => { if (stateRef.current === "speaking") done(); }, dur);
      }
    } catch {
      transitionTo("speaking");
      setPhraseText("Gateway's not answering, Champ — is it running on :8765?");
      setTimeout(() => { transitionTo("idle"); if (awakeRef.current) wantListenRef.current(); }, 4000);
    } finally {
      setSending(false);
    }
  }, [transitionTo]);

  // ─── Voice: clap-to-wake + speech conversation ───────────────────────────
  // Speak a short line in Donald's voice via the gateway's /api/voice, and run
  // `after` once it finishes (used for the "Donald's here" wake announcement).
  const speakLine = useCallback(async (text: string, after?: () => void) => {
    transitionTo("speaking");
    setPhraseText(text);
    try {
      const res = await fetch("/gw/api/voice", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error("voice http " + res.status);
      const buf = await res.arrayBuffer();
      const audio = new Audio(URL.createObjectURL(new Blob([buf], { type: "audio/mpeg" })));
      audioRef.current = audio;
      audio.onended = () => after?.();
      audio.onerror = () => after?.();
      await audio.play().catch(() => after?.());
    } catch {
      setTimeout(() => after?.(), 800);
    }
  }, [transitionTo]);

  const goDormant = useCallback(() => {
    awakeRef.current = false;
    listeningRef.current = false;
    try { recognitionRef.current?.stop(); } catch {}
    transitionTo("idle");
    setPhraseText("");
    setVoiceMsg("Dormant — clap loudly to wake Donald 👏");
  }, [transitionTo]);

  const startListening = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec || !awakeRef.current) return;
    gotSpeechRef.current = false;
    listeningRef.current = true;
    transitionTo("listening");
    setVoiceMsg("Listening… just talk");
    try { rec.start(); } catch { /* already started */ }
  }, [transitionTo]);

  const onClap = useCallback(() => {
    if (awakeRef.current) return;          // already awake
    awakeRef.current = true;
    noSpeechRef.current = 0;
    setVoiceMsg("");
    speakLine("Donald's here.", () => startListening());
  }, [speakLine, startListening]);

  // Keep the cross-call refs current.
  useEffect(() => { sendRef.current = send; }, [send]);
  useEffect(() => { wantListenRef.current = startListening; }, [startListening]);

  const enableVoice = useCallback(async () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setVoiceMsg("Speech recognition needs Chrome — Safari won't do it reliably.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const AC = (window as any).AudioContext || (window as any).webkitAudioContext;
      const ctx = new AC();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyserRef.current = analyser;
      clapDataRef.current = new Uint8Array(analyser.fftSize);

      // Speech recognition (one phrase at a time).
      const rec = new SR();
      rec.lang = "en-US";
      rec.interimResults = true;
      rec.continuous = false;
      rec.onresult = (e: any) => {
        let finalT = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalT += r[0].transcript;
          else setPhraseText(r[0].transcript);
        }
        if (finalT.trim()) {
          gotSpeechRef.current = true;
          listeningRef.current = false;
          try { rec.stop(); } catch {}
          sendRef.current(finalT.trim());
        }
      };
      rec.onerror = (e: any) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          setVoiceMsg("Mic blocked — allow microphone access and reload.");
          goDormant();
        }
      };
      rec.onend = () => {
        // Ended without a final phrase while awake → retry, then sleep after a few.
        if (listeningRef.current && awakeRef.current && !gotSpeechRef.current) {
          noSpeechRef.current += 1;
          if (noSpeechRef.current >= 3) { goDormant(); }
          else { setTimeout(() => startListening(), 250); }
        }
      };
      recognitionRef.current = rec;

      // Clap detector loop: watch the mic's peak amplitude; a loud, brief spike
      // while dormant wakes Donald.
      const loop = () => {
        const a = analyserRef.current, d = clapDataRef.current;
        if (a && d) {
          a.getByteTimeDomainData(d);
          let peak = 0;
          for (let i = 0; i < d.length; i++) {
            const v = Math.abs(d[i] - 128) / 128;
            if (v > peak) peak = v;
          }
          const now = Date.now();
          if (!awakeRef.current && peak >= CLAP_THRESHOLD && now - lastClapRef.current > 1500) {
            lastClapRef.current = now;
            onClap();
          }
        }
        clapRafRef.current = requestAnimationFrame(loop);
      };
      loop();

      setVoiceOn(true);
      setVoiceMsg("Dormant — clap loudly to wake Donald 👏");
    } catch {
      setVoiceMsg("Couldn't get the mic — check the browser's mic permission.");
    }
  }, [onClap, startListening, goDormant]);

  // Cleanup mic/loop on unmount.
  useEffect(() => {
    return () => {
      if (clapRafRef.current) cancelAnimationFrame(clapRafRef.current);
      try { recognitionRef.current?.abort?.(); } catch {}
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // Canvas — must re-run after boot; canvas isn't mounted during the boot screen
  useEffect(() => {
    if (!booted) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      canvas.width = r.width * dpr;
      canvas.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const initParticles = (count: number) => {
      const arr = [];
      for (let i = 0; i < count; i++) {
        arr.push({
          angle: rand(0, Math.PI * 2),
          radius: rand(0.25, 0.55),
          speed: rand(0.002, 0.012) * (Math.random() > 0.5 ? 1 : -1),
          size: rand(0.5, 2.2),
          brightness: rand(0.3, 1),
          orbit: rand(-0.3, 0.3),
          phase: rand(0, Math.PI * 2),
          layer: Math.floor(rand(0, 3)),
        });
      }
      return arr;
    };
    particlesRef.current = initParticles(350);

    const draw = () => {
      const W = canvas.width / dpr;
      const H = canvas.height / dpr;
      const cx = W / 2;
      const cy = H / 2;
      const minDim = Math.min(W, H);
      const frame = frameRef.current++;
      const time = frame * 0.01;

      const e = energyRef.current;
      e.current = lerp(e.current, e.target, 0.03);
      const rs = ringSpeedRef.current;
      rs.current = lerp(rs.current, rs.target, 0.03);
      const pc = particleCountRef.current;
      pc.current = lerp(pc.current, pc.target, 0.03);
      const sr = sparkRateRef.current;
      sr.current = lerp(sr.current, sr.target, 0.03);

      const energy = e.current;
      const coreRadius = minDim * 0.06;

      ctx.clearRect(0, 0, W, H);

      const atm = ctx.createRadialGradient(cx, cy, 0, cx, cy, minDim * 0.5);
      atm.addColorStop(0, `rgba(212,160,32,${0.04 + energy * 0.04})`);
      atm.addColorStop(0.3, `rgba(180,120,10,${0.02 + energy * 0.02})`);
      atm.addColorStop(0.7, `rgba(139,94,10,${0.008})`);
      atm.addColorStop(1, "transparent");
      ctx.fillStyle = atm;
      ctx.fillRect(0, 0, W, H);

      const ringCount = 5;
      for (let i = 0; i < ringCount; i++) {
        const r = minDim * (0.12 + i * 0.07);
        const rot = time * rs.current * (i % 2 === 0 ? 1 : -1) * (0.5 + i * 0.15);
        const wobble = Math.sin(time * 0.7 + i * 1.3) * 0.08;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(rot);
        ctx.scale(1, 0.92 + wobble);

        const segments = 3 + i;
        const gapSize = 0.15 + i * 0.03;
        for (let s = 0; s < segments; s++) {
          const segStart = (s / segments) * Math.PI * 2 + Math.sin(time * 0.3 + i) * 0.2;
          const segEnd = segStart + (Math.PI * 2 / segments) * (1 - gapSize);

          ctx.beginPath();
          ctx.arc(0, 0, r, segStart, segEnd);
          const alpha = (0.08 + energy * 0.12) * (1 - i * 0.12);
          ctx.strokeStyle = `rgba(232,168,50,${alpha})`;
          ctx.lineWidth = 1.2 - i * 0.1;
          ctx.stroke();

          for (const a of [segStart, segEnd]) {
            const tx = Math.cos(a) * r;
            const ty = Math.sin(a) * r;
            const tx2 = Math.cos(a) * (r + 4 + energy * 4);
            const ty2 = Math.sin(a) * (r + 4 + energy * 4);
            ctx.beginPath();
            ctx.moveTo(tx, ty);
            ctx.lineTo(tx2, ty2);
            ctx.strokeStyle = `rgba(255,204,68,${alpha * 0.7})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }
        ctx.restore();
      }

      const filCount = 8 + Math.floor(energy * 8);
      for (let i = 0; i < filCount; i++) {
        const baseAngle = (i / filCount) * Math.PI * 2 + time * 0.2;
        const len = minDim * (0.1 + energy * 0.15 + Math.sin(time * 2 + i * 1.7) * 0.04);

        ctx.beginPath();
        ctx.moveTo(cx, cy);

        const steps = 12;
        for (let s = 1; s <= steps; s++) {
          const t = s / steps;
          const wanderX = Math.sin(time * 3 + i * 2.1 + s * 0.8) * t * 12 * energy;
          const wanderY = Math.cos(time * 2.5 + i * 1.7 + s * 1.1) * t * 12 * energy;
          const px = cx + Math.cos(baseAngle) * len * t + wanderX;
          const py = cy + Math.sin(baseAngle) * len * t + wanderY;
          ctx.lineTo(px, py);
        }

        const alpha = 0.06 + energy * 0.08;
        ctx.strokeStyle = `rgba(255,200,80,${alpha})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }

      const visibleCount = Math.floor(pc.current);
      for (let i = 0; i < Math.min(visibleCount, particlesRef.current.length); i++) {
        const p = particlesRef.current[i];
        p.angle += p.speed * (0.5 + energy);

        const orbR = minDim * p.radius * (0.9 + Math.sin(time + p.phase) * 0.1);
        const tiltY = Math.sin(p.orbit + time * 0.1) * 0.35;

        const px = cx + Math.cos(p.angle) * orbR;
        const py = cy + Math.sin(p.angle) * orbR * (0.65 + tiltY);

        const dist = Math.sqrt((px - cx) ** 2 + (py - cy) ** 2);
        const maxDist = minDim * 0.55;
        if (dist > maxDist) continue;

        const alpha = p.brightness * (0.3 + energy * 0.5) * (1 - dist / maxDist);
        const sz = p.size * (0.8 + energy * 0.5);

        ctx.beginPath();
        ctx.arc(px, py, sz, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,${160 + Math.floor(p.brightness * 60)},${20 + Math.floor(p.brightness * 40)},${alpha})`;
        ctx.fill();

        if (sz > 1.5) {
          ctx.beginPath();
          ctx.arc(px, py, sz * 3, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255,200,80,${alpha * 0.15})`;
          ctx.fill();
        }
      }

      if (Math.random() < sr.current) {
        const angle = rand(0, Math.PI * 2);
        sparksRef.current.push({
          x: cx, y: cy, vx: Math.cos(angle) * rand(1, 4) * (0.5 + energy),
          vy: Math.sin(angle) * rand(1, 4) * (0.5 + energy),
          life: 1, decay: rand(0.01, 0.03), size: rand(0.5, 1.5),
        });
      }
      sparksRef.current = sparksRef.current.filter(s => {
        s.x += s.vx; s.y += s.vy;
        s.vx *= 0.98; s.vy *= 0.98;
        s.life -= s.decay;
        if (s.life <= 0) return false;

        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size * s.life, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,220,100,${s.life * 0.6})`;
        ctx.fill();

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(s.x - s.vx * 3, s.y - s.vy * 3);
        ctx.strokeStyle = `rgba(255,180,50,${s.life * 0.25})`;
        ctx.lineWidth = s.size * 0.6;
        ctx.stroke();

        return true;
      });

      const cg1 = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius * 6);
      cg1.addColorStop(0, `rgba(255,220,120,${0.15 + energy * 0.15})`);
      cg1.addColorStop(0.3, `rgba(232,168,50,${0.06 + energy * 0.06})`);
      cg1.addColorStop(1, "transparent");
      ctx.fillStyle = cg1;
      ctx.fillRect(cx - coreRadius * 6, cy - coreRadius * 6, coreRadius * 12, coreRadius * 12);

      const cg2 = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius * 2.5);
      cg2.addColorStop(0, `rgba(255,240,176,${0.5 + energy * 0.3})`);
      cg2.addColorStop(0.4, `rgba(232,168,50,${0.25 + energy * 0.15})`);
      cg2.addColorStop(1, "transparent");
      ctx.fillStyle = cg2;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius * 2.5, 0, Math.PI * 2);
      ctx.fill();

      const pulse = 1 + Math.sin(time * 2) * 0.12 * energy;
      const cg3 = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius * pulse);
      cg3.addColorStop(0, `rgba(255,255,240,${0.9 + energy * 0.1})`);
      cg3.addColorStop(0.3, `rgba(255,240,176,0.7)`);
      cg3.addColorStop(0.7, `rgba(232,168,50,0.3)`);
      cg3.addColorStop(1, "transparent");
      ctx.fillStyle = cg3;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius * pulse, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius * 0.25 * pulse, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,255,255,${0.8 + energy * 0.2})`;
      ctx.fill();

      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => { window.removeEventListener("resize", resize); if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [booted]);

  return (
    <div
      onClick={booted ? () => inputRef.current?.focus() : undefined}
      style={{
        width: "100%", height: "100vh", background: BG, position: "relative", overflow: "hidden",
        fontFamily: "'SF Mono','Cascadia Code','Fira Code','JetBrains Mono',monospace",
        cursor: state === "idle" && booted ? "pointer" : "default", userSelect: "none",
      }}
    >
      <style>{`
        @keyframes fadeIn { from{opacity:0} to{opacity:1} }
        @keyframes fadeInUp { from{opacity:0;transform:translateY(14px)} to{opacity:1;transform:translateY(0)} }
        @keyframes subtlePulse { 0%,100%{opacity:0.3} 50%{opacity:0.7} }
        @keyframes cursorBlink { 0%,100%{opacity:1} 50%{opacity:0} }
      `}</style>

      {!booted && (
        <div style={{
          position:"absolute",inset:0,zIndex:50,background:BG,
          display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",
          opacity: bootProgress >= 1 ? 0 : 1, transition:"opacity 0.8s ease",
        }}>
          <div style={{ fontSize:14,letterSpacing:10,color:GOLD,marginBottom:28 }}>D.O.N.A.L.D.</div>
          <div style={{ width:180,height:2,background:"rgba(212,160,32,0.1)",borderRadius:1,overflow:"hidden" }}>
            <div style={{
              height:"100%",background:`linear-gradient(90deg,${DEEP},${GOLD},${BRIGHT})`,
              width:`${bootProgress*100}%`,transition:"width 0.1s",boxShadow:`0 0 10px ${GOLD}`,
            }} />
          </div>
          <div style={{ fontSize:9,color:DIM_TEXT,marginTop:12,letterSpacing:3 }}>INITIALIZING CORE</div>
        </div>
      )}

      {booted && (
        <>
          <div style={{
            position:"absolute",top:"8%",left:0,right:0,
            display:"flex",flexDirection:"column",alignItems:"center",gap:6,
            animation:"fadeInUp 1s ease-out", zIndex:2,
          }}>
            <div style={{
              fontSize:22,fontWeight:700,letterSpacing:16,color:GOLD,
              textShadow:`0 0 40px rgba(212,160,32,0.35)`,
            }}>
              D.O.N.A.L.D.
            </div>
            <div style={{ fontSize:8,letterSpacing:5,color:DIM_TEXT }}>
              DIGITAL OPERATIONS NEURAL ADAPTIVE LEARNING DAEMON
            </div>
          </div>

          <canvas ref={canvasRef} style={{
            position:"absolute",inset:0,width:"100%",height:"100%",
            animation:"fadeIn 1.5s ease-out",
          }} />

          <div style={{
            position:"absolute",bottom:"18%",left:0,right:0,
            display:"flex",flexDirection:"column",alignItems:"center",gap:10,
            animation:"fadeInUp 1.2s ease-out",zIndex:2,
          }}>
            {displayedPhrase && (
              <div style={{
                fontSize:14,color:"rgba(255,220,150,0.8)",maxWidth:380,
                textAlign:"center",lineHeight:1.7,letterSpacing:0.5,
                animation:"fadeIn 0.5s ease-out",marginBottom:8,
              }}>
                "{displayedPhrase}"
                {displayedPhrase.length < phraseText.length && (
                  <span style={{ animation:"cursorBlink 0.8s infinite",marginLeft:2 }}>▌</span>
                )}
              </div>
            )}
            <div style={{ display:"flex",alignItems:"center",gap:8 }}>
              <div style={{
                width:5,height:5,borderRadius:"50%",
                background: state==="idle" ? GOLD : BRIGHT,
                boxShadow:`0 0 8px ${state==="idle"?GOLD:BRIGHT}`,
                animation: state!=="idle" ? "subtlePulse 0.6s infinite" : "none",
              }} />
              <span style={{ fontSize:10,letterSpacing:4,color:MED_TEXT }}>{statusText}</span>
            </div>
          </div>

          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position:"absolute",bottom:"12.5%",left:0,right:0,
              display:"flex",flexDirection:"column",alignItems:"center",gap:8,zIndex:3,
            }}
          >
            {!voiceOn ? (
              <button
                onClick={enableVoice}
                style={{
                  padding:"9px 18px",background:"rgba(212,160,32,0.1)",
                  border:`1px solid rgba(212,160,32,0.5)`,borderRadius:20,
                  color:"#ffe9b0",fontSize:12,letterSpacing:1,cursor:"pointer",
                  fontFamily:"inherit",
                }}
              >
                🎤 Enable clap-to-wake + voice
              </button>
            ) : (
              <div
                onClick={() => { if (!awakeRef.current) onClap(); }}
                style={{
                  fontSize:11,letterSpacing:2,color:MED_TEXT,cursor:"pointer",
                  textAlign:"center",
                }}
              >
                {voiceMsg || " "}{!awakeRef.current && " · (or click here to wake)"}
              </div>
            )}
          </div>

          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position:"absolute",bottom:"7%",left:0,right:0,
              display:"flex",justifyContent:"center",zIndex:3,
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
              placeholder={sending ? "Donald is working…" : "Talk to Donald — hit Enter"}
              disabled={sending}
              style={{
                width:"min(520px,80%)",padding:"12px 18px",
                background:"rgba(212,160,32,0.06)",
                border:`1px solid rgba(212,160,32,0.35)`,borderRadius:12,
                color:"#ffe9b0",fontSize:14,outline:"none",
                fontFamily:"inherit",letterSpacing:0.5,
                boxShadow:"0 0 24px rgba(212,160,32,0.08)",
                opacity: sending ? 0.6 : 1,
              }}
            />
          </div>

          {[
            {top:16,left:16,borderTop:`1px solid ${GOLD}18`,borderLeft:`1px solid ${GOLD}18`},
            {top:16,right:16,borderTop:`1px solid ${GOLD}18`,borderRight:`1px solid ${GOLD}18`},
            {bottom:16,left:16,borderBottom:`1px solid ${GOLD}18`,borderLeft:`1px solid ${GOLD}18`},
            {bottom:16,right:16,borderBottom:`1px solid ${GOLD}18`,borderRight:`1px solid ${GOLD}18`},
          ].map((s,i) => (
            <div key={i} style={{ position:"absolute",width:18,height:18,...s,pointerEvents:"none" }} />
          ))}
        </>
      )}
    </div>
  );
}
