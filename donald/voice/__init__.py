"""Tier 2 — the voice loop: speak to Donald, hear it answer.

Same agent as the text loop (Tier 0), just with ears (Deepgram) and a mouth
(ElevenLabs) bolted on. Say "goodbye" / "stop listening" to exit.

Run with:  donald voice   (after `pip install -e ".[voice]"` and setting keys)
"""

from __future__ import annotations

from ..conversation import Conversation

EXIT_PHRASES = {"goodbye", "stop listening", "go to sleep", "exit", "quit"}


def run_voice(donald) -> None:
    from .audio import play_pcm, record_until_silence
    from .stt import DeepgramSTT
    from .tts import ElevenLabsTTS

    config = donald.config
    if config.brain == "mock":
        print(
            "Note: running with the mock brain. Set ANTHROPIC_API_KEY for real "
            "answers; voice still works for testing the audio path."
        )

    stt = DeepgramSTT(config)
    tts = ElevenLabsTTS(config)
    convo = Conversation(donald.agent)

    def say(text: str) -> None:
        print(f"Donald: {text}")
        try:
            play_pcm(tts.synthesize(text))
        except Exception as exc:  # don't let a TTS hiccup kill the loop
            print(f"   (couldn't speak: {exc})")

    say("I'm listening.")
    while True:
        try:
            wav = record_until_silence()
        except KeyboardInterrupt:
            say("Goodbye.")
            return

        text = stt.transcribe(wav).strip()
        if not text:
            continue
        print(f"You: {text}")

        if text.lower().strip(" .!") in EXIT_PHRASES:
            say("Goodbye.")
            return

        reply = convo.send(text)
        say(reply)
