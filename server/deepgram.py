import asyncio
import json
import logging
from deepgram import DeepgramClient, LiveTranscriptionEvents
from server.config import settings

logger = logging.getLogger(__name__)


class DeepgramSTT:
    def __init__(self):
        self.dg_client = DeepgramClient(api_key=settings.deepgram_api_key)
        self.current_transcript = ""
        self.is_final = False

    async def stream_stt(self, audio_frames_queue):
        """
        Stream audio frames to Deepgram and yield transcripts as they arrive.
        Expects audio_frames_queue to be an asyncio.Queue with base64-encoded PCM frames.

        Yields (transcript_text, is_final).
        """
        self.current_transcript = ""
        self.is_final = False

        try:
            # Open a live connection to Deepgram
            async with self.dg_client.live.live(
                {
                    "model": "nova-2",
                    "language": "en",
                    "encoding": "linear16",
                    "sample_rate": 16000,
                    "interim_results": True,
                }
            ) as dg_connection:

                # Set up event handlers
                def on_message(self, result, **kwargs):
                    transcript = result.channel.alternatives[0].transcript if result.channel.alternatives else ""

                    if not result.speech_final:
                        # Interim result
                        self.current_transcript = transcript
                        self.is_final = False
                    else:
                        # Final result
                        self.current_transcript = transcript
                        self.is_final = True

                def on_error(self, error, **kwargs):
                    logger.error(f"Deepgram error: {error}")

                def on_close(self, close, **kwargs):
                    logger.info("Deepgram connection closed")

                dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
                dg_connection.on(LiveTranscriptionEvents.Error, on_error)
                dg_connection.on(LiveTranscriptionEvents.Close, on_close)

                # Consume audio frames from queue and send to Deepgram
                while True:
                    try:
                        # Get frame from queue with timeout
                        frame = await asyncio.wait_for(audio_frames_queue.get(), timeout=0.1)

                        # Decode base64 frame and send to Deepgram
                        import base64
                        audio_bytes = base64.b64decode(frame)
                        dg_connection.send(audio_bytes)

                    except asyncio.TimeoutError:
                        # No frames in queue; check if we should keep listening
                        # In a real implementation, this would check a stop flag
                        continue

                    except Exception as e:
                        logger.error(f"Error in STT stream: {e}")
                        break

        except Exception as e:
            logger.error(f"Deepgram connection error: {e}")

    async def get_final_transcript(self) -> str:
        """Get the final transcript after streaming ends."""
        return self.current_transcript
