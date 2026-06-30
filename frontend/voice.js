// Voice loop: microphone capture, Deepgram streaming, TTS playback
// Dual-path audio: <audio> element for audible output, BufferSource for analyser

import { getAudioContext, getAnalyser } from '/static/scene.js?v=20260630-initial';

let ws;
let mediaStream;
let audioProcessor;
let isListening = false;
let sessionToken;

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const TOKEN = new URLSearchParams(window.location.search).get('token') || localStorage.getItem('donald_token') || 'default-token';

export async function setupVoiceLoop() {
    console.log('[Voice] Initializing voice loop...');

    // Store token in localStorage for future sessions
    localStorage.setItem('donald_token', TOKEN);

    // Ensure AudioContext is initialized
    const audioCtx = getAudioContext();
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume();
    }

    // Register service worker
    if ('serviceWorker' in navigator) {
        try {
            await navigator.serviceWorker.register('/static/sw.js');
            console.log('[Voice] Service worker registered');
        } catch (e) {
            console.warn('[Voice] Service worker registration failed:', e);
        }
    }

    // Connect WebSocket with token
    connectWebSocket();

    // Orb click handler: start/stop listening
    const canvas = document.getElementById('orbCanvas');
    canvas.addEventListener('click', handleOrbClick);

    console.log('[Voice] Voice loop ready');
}

function connectWebSocket() {
    ws = new WebSocket(`${WS_URL}?token=${encodeURIComponent(TOKEN)}`);
    ws.onopen = () => {
        console.log('[WS] Connected');
    };
    ws.onmessage = handleWebSocketMessage;
    ws.onerror = (error) => {
        console.error('[WS] Error:', error);
    };
    ws.onclose = () => {
        console.log('[WS] Disconnected');
        // Attempt reconnect in 2 seconds
        setTimeout(connectWebSocket, 2000);
    };
}

async function handleOrbClick(e) {
    const audioCtx = getAudioContext();

    // Ensure AudioContext is resumed (iOS quirk: user-activation window)
    if (audioCtx && audioCtx.state === 'suspended') {
        await audioCtx.resume();
    }

    // Prime audio element (iOS quirk: synchronous play() in gesture)
    const audioEl = document.getElementById('tts');
    audioEl.play().then(() => {
        audioEl.pause();
    }).catch(() => {});

    // Toggle listening
    if (isListening) {
        stopListening();
    } else {
        startListening();
    }
}

async function startListening() {
    console.log('[Voice] Starting listening...');

    isListening = true;
    updateStatus('listening');
    hideTapHint();

    try {
        // Request microphone access
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: false,
            },
        });

        // Send start_listening to server
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'start_listening' }));
        }

        // Set up Web Audio for capture and frame transmission
        const audioCtx = getAudioContext();
        const source = audioCtx.createMediaStreamSource(mediaStream);

        // AudioWorklet for frame-by-frame capture (16 kHz, 256-sample frames)
        // For now, use a ScriptProcessor as fallback (deprecated but works)
        const frameSize = 256;
        audioProcessor = audioCtx.createScriptProcessor(frameSize, 1, 1);

        audioProcessor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            // Downsample to 16 kHz if needed and send frames
            sendAudioFrame(inputData);
        };

        source.connect(audioProcessor);
        audioProcessor.connect(audioCtx.destination);

    } catch (error) {
        console.error('[Voice] Error starting listening:', error);
        updateStatus('error');
        isListening = false;
        showTapHint();
    }
}

function stopListening() {
    console.log('[Voice] Stopping listening...');

    isListening = false;

    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }

    if (audioProcessor) {
        audioProcessor.disconnect();
        audioProcessor = null;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop_listening' }));
    }

    updateStatus('processing');
}

function sendAudioFrame(frameData) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // Convert PCM to base64 for transmission
    const base64Frame = btoa(String.fromCharCode(...new Uint8Array(frameData.buffer)));

    ws.send(JSON.stringify({
        type: 'audio_frame',
        data: base64Frame,
    }));
}

async function handleWebSocketMessage(event) {
    const msg = JSON.parse(event.data);
    const type = msg.type;

    console.log('[WS] Message:', type);

    switch (type) {
        case 'start_mic':
            // Server acknowledged; listening is active
            updateStatus('listening');
            break;

        case 'transcript':
            // User's transcript received
            if (msg.role === 'user') {
                updateTranscript(msg.text);
            }
            break;

        case 'transcript_delta':
            // Streaming agent response
            appendTranscript(msg.text);
            break;

        case 'status':
            updateStatus(msg.state);
            break;

        case 'speak':
            // Server has cached TTS response; fetch and play it
            await playTTS(msg.turn_id);
            break;

        case 'tool_start':
            showActionChip(msg.tool_name, 'calling', `${msg.tool_name}…`);
            break;

        case 'tool_end':
            if (msg.status === 'success') {
                showActionChip(msg.tool_name, 'success', msg.result);
            } else {
                showActionChip(msg.tool_name, 'error', msg.error || 'Error');
            }
            break;

        case 'confirm_request':
            showActionChip('confirm', 'confirm', msg.summary);
            break;

        default:
            console.warn('[WS] Unknown message type:', type);
    }
}

async function playTTS(turnId) {
    console.log('[TTS] Playing turn:', turnId);

    try {
        // Fetch MP3 from /api/tts/{turn_id}
        const response = await fetch(`/api/tts/${turnId}?token=${encodeURIComponent(TOKEN)}`);
        if (!response.ok) {
            throw new Error(`TTS fetch failed: ${response.status}`);
        }

        const mp3Bytes = await response.arrayBuffer();
        const audioCtx = getAudioContext();
        const analyser = getAnalyser();

        // Audible path: <audio> element with MP3 blob
        const blob = new Blob([mp3Bytes], { type: 'audio/mpeg' });
        const audioUrl = URL.createObjectURL(blob);
        const audioEl = document.getElementById('tts');
        audioEl.src = audioUrl;
        audioEl.play().catch(err => {
            console.error('[TTS] Play error:', err);
        });

        // Analysis path (parallel): decode clone of bytes for analyser
        try {
            const buffer = await audioCtx.decodeAudioData(mp3Bytes.slice(0));
            const src = audioCtx.createBufferSource();
            src.buffer = buffer;
            src.connect(analyser); // Side-branch only — no destination
            src.start();

            // Clean up when done
            src.onended = () => {
                console.log('[TTS] Playback ended');
                updateStatus('idle');
                showTapHint();
            };
        } catch (e) {
            console.warn('[TTS] Could not decode for analyser:', e);
        }

    } catch (error) {
        console.error('[TTS] Error:', error);
        updateStatus('error');
    }
}

// UI helpers
function updateStatus(state) {
    const pill = document.getElementById('statusPill');
    pill.textContent = state.toUpperCase();
}

function updateTranscript(text) {
    const el = document.getElementById('transcript');
    el.textContent = text;
}

function appendTranscript(text) {
    const el = document.getElementById('transcript');
    el.textContent = (el.textContent || '') + text;
}

function hideTapHint() {
    const hint = document.getElementById('tapHint');
    hint.classList.add('hidden');
}

function showTapHint() {
    const hint = document.getElementById('tapHint');
    hint.classList.remove('hidden');
}

function showActionChip(toolName, state, label) {
    const chip = document.getElementById('actionChip');
    chip.className = `${state}`;

    let html = '';
    if (state === 'calling') {
        html = `<span class="spinner"></span>${label}`;
    } else if (state === 'confirm') {
        html = `⚠ ${label}`;
    } else if (state === 'success') {
        html = `✓ ${label}`;
    } else {
        html = `✕ ${label}`;
    }

    chip.innerHTML = html;
    chip.classList.add('visible');

    if (state !== 'confirm') {
        setTimeout(() => chip.classList.remove('visible'), 3000);
    }
}
