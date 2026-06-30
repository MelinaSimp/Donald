"""Voice layer (Tier 3).

Wraps the existing brain — does not rewrite it. Input arrives as transcribed
speech instead of typed text; output is spoken aloud as well as printed. The
agent in the middle is untouched: a spoken turn feeds the same Agent.respond a
typed turn uses.

Each provider sits behind a seam, like the model provider:
  stt.py  -> "give me audio, get back text"  (Deepgram)
  tts.py  -> "give me text, play it aloud"    (ElevenLabs)
  audio.py-> microphone capture + playback     (push-to-talk)
"""
