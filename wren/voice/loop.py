"""The spoken-turn loop (Tier 3).

A spoken turn: capture (push-to-talk) -> transcribe (Deepgram) -> run the SAME
brain -> speak the reply (ElevenLabs). The transcript of what Wren *heard* is
shown next to its reply while building, so when it answers the wrong question you
can see whether the ears or the brain was at fault.

The typed interface stays alive: at the prompt, type to send text, or press Enter
to talk. It's how you debug without talking to your computer, and a graceful
fallback when audio misbehaves.
"""
from __future__ import annotations

from ..app import App


def run_voice(app: App) -> None:
    try:
        from .audio import record_until_enter
        from .stt import build_stt
        from .tts import build_tts
    except ImportError as e:
        print(f"Voice deps not installed ({e}). Run: pip install -r requirements-voice.txt")
        return

    try:
        stt = build_stt(app.config)
        tts = build_tts(app.config)
    except RuntimeError as e:
        print(f"Voice not configured: {e}")
        return

    show = bool(app.config.get("voice.show_transcript", True))
    print(f"\n🎙  {app.config.get('assistant.name', 'Wren')} — voice mode.")
    print("   Type to send text, or press Enter on an empty line to talk. 'q' to quit.\n")

    while True:
        try:
            typed = input("you ▷ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if typed.lower() in ("q", "quit", "exit"):
            break

        if typed:
            user_text = typed
        else:
            wav = record_until_enter()
            user_text = stt.transcribe(wav)
            if show:
                print(f"   (heard: \"{user_text}\")")
            if not user_text:
                print("   (heard nothing — try again)")
                continue

        print(f"{app.config.get('assistant.name', 'Wren')} ▷ ", end="", flush=True)
        reply = app.agent.respond(user_text, on_text=lambda t: print(t, end="", flush=True),
                                  source="voice")
        print()

        # Don't listen while speaking (Tier 3): speak in the background and let
        # the user press Enter to cut it off and start a new turn.
        tts.speak_async(reply)
        try:
            input()  # press Enter to interrupt playback
            tts.stop()
        except (EOFError, KeyboardInterrupt):
            tts.stop()
            break

    print(app.audit.cost_line())
