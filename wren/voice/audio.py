"""Microphone capture for push-to-talk (Tier 3).

Push-to-talk means you never have to guess when speech started or finished — a
big simplification worth keeping until everything else is solid. True hold-a-key
needs raw key events (and often root on Linux), so the reliable baseline is a
press-to-start / press-to-stop toggle on Enter: you press Enter, you see
"recording…", you press Enter again to stop. Same guarantee (explicit
boundaries), no platform key-grab.

Returns 16-bit mono WAV bytes ready for the STT seam.
"""
from __future__ import annotations

import io
import threading
import wave

SAMPLE_RATE = 16_000
CHANNELS = 1


def record_until_enter(prompt: str = "Press Enter to start, Enter again to stop.") -> bytes:
    import numpy as np
    import sounddevice as sd

    input(f"{prompt}\n  ▶ ready — Enter to start: ")
    frames: list = []
    stop = threading.Event()

    def callback(indata, _frames, _time, _status):
        frames.append(indata.copy())

    print("  ● recording… (Enter to stop)")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                        callback=callback):
        # Block on stdin in a thread so the audio stream keeps filling `frames`.
        t = threading.Thread(target=lambda: (input(), stop.set()), daemon=True)
        t.start()
        stop.wait()
    print("  ■ stopped.")

    if not frames:
        return _wav_bytes(b"")
    audio = np.concatenate(frames, axis=0)
    return _wav_bytes(audio.tobytes())


def _wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()
