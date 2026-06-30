"""Microphone capture and speaker playback for Tier 2.

Kept deliberately small: record from the mic until the speaker goes quiet
(energy-based voice activity), and play raw PCM out. Heavy audio deps
(``sounddevice``, ``numpy``) are imported lazily so the rest of Donald imports
fine without the voice extras installed.
"""

from __future__ import annotations

import io
import wave

SAMPLE_RATE = 16000  # 16 kHz mono — what Deepgram and ElevenLabs PCM use here.


def _require_audio():
    try:
        import numpy as np  # noqa: F401
        import sounddevice as sd  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise RuntimeError(
            "Voice needs the audio extras. Install with: pip install -e \".[voice]\""
        ) from exc
    return np, sd


def record_until_silence(
    max_seconds: float = 15.0,
    silence_seconds: float = 1.2,
    start_threshold: float = 0.015,
) -> bytes:
    """Record mic audio, stopping after a stretch of silence. Returns WAV bytes.

    Returns an empty bytes object if nothing above the threshold was spoken.
    """
    np, sd = _require_audio()

    block = int(SAMPLE_RATE * 0.1)  # 100 ms blocks
    chunks: list = []
    silent_for = 0.0
    started = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=block
    ) as stream:
        elapsed = 0.0
        while elapsed < max_seconds:
            data, _ = stream.read(block)
            elapsed += 0.1
            level = float(np.sqrt(np.mean(np.square(data))))
            if level >= start_threshold:
                started = True
                silent_for = 0.0
                chunks.append(data.copy())
            elif started:
                silent_for += 0.1
                chunks.append(data.copy())
                if silent_for >= silence_seconds:
                    break

    if not started or not chunks:
        return b""

    audio = np.concatenate(chunks, axis=0)
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    return _to_wav(pcm16.tobytes())


def _to_wav(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def play_pcm(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    """Play raw signed-16-bit mono PCM through the default speaker."""
    np, sd = _require_audio()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16)
    sd.play(audio, sample_rate)
    sd.wait()
