"""Donald — a personal Jarvis-style assistant, built tier by tier.

Tier 0  text conversation loop      donald.conversation
Tier 1  tool registry + tools       donald.tools
Tier 2  voice (Deepgram/ElevenLabs) donald.voice
Tier 3  persistent memory (SQLite)  donald.memory
Tier 4  proactive background loop   donald.proactive
Tier 5  safety rails                donald.safety
"""

__version__ = "0.1.0"
