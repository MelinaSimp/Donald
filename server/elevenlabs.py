import asyncio
import logging
import aiohttp
from server.config import settings

logger = logging.getLogger(__name__)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default); customize as needed


class ElevenLabsTTS:
    def __init__(self):
        self.api_key = settings.elevenlabs_api_key

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to MP3 (mp3_44100_128).

        Returns MP3 bytes.
        """
        url = f"{ELEVENLABS_API_URL}/text-to-speech/{VOICE_ID}/stream"

        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        mp3_bytes = await response.read()
                        logger.info(f"TTS synthesized {len(mp3_bytes)} bytes")
                        return mp3_bytes
                    else:
                        error_text = await response.text()
                        logger.error(f"ElevenLabs error {response.status}: {error_text}")
                        return b""

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return b""

    async def stream_synthesize(self, text: str):
        """
        Synthesize text and stream MP3 chunks.

        Yields MP3 bytes as they arrive.
        """
        url = f"{ELEVENLABS_API_URL}/text-to-speech/{VOICE_ID}/stream"

        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        async for chunk in response.content.iter_chunked(1024):
                            yield chunk
                    else:
                        error_text = await response.text()
                        logger.error(f"ElevenLabs error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"TTS stream error: {e}")
