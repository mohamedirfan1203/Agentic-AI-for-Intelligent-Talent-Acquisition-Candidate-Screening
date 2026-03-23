"""
Voice Agent  —  Deepgram Voice-Agent Integration
=================================================
Responsibilities:
  • Build and expose the Deepgram Voice-Agent WebSocket URL
  • Return the initialisation Settings payload
  • Keep all Deepgram-specific logic in one place

The actual audio proxying happens in the FastAPI route (app/routes/voice.py)
which opens two WebSocket connections:
  Browser  ←→  FastAPI  ←→  Deepgram Voice-Agent API
"""

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("agents.voice_agent")

DEEPGRAM_VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

DESCRIPTION = (
    "Manages a real-time voice conversation with callers via the Deepgram "
    "Voice-Agent API.  Handles STT (speech-to-text), LLM reasoning, and "
    "TTS (text-to-speech) in a single WebSocket session."
)


class VoiceAgent:
    """
    Lightweight wrapper around the Deepgram Voice-Agent configuration.

    The heavy lifting (bidirectional WebSocket proxy) is done inside the
    FastAPI route so that native async WebSocket support can be used.
    This class provides helpers that the route imports.
    """

    DESCRIPTION = DESCRIPTION

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_deepgram_ws_url(self) -> str:
        """Return the Deepgram Voice-Agent WebSocket endpoint."""
        return DEEPGRAM_VOICE_AGENT_URL

    def get_api_key(self) -> str:
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise ValueError(
                "[VoiceAgent] DEEPGRAM_API_KEY is not set in environment variables."
            )
        return api_key


    def build_headers(self) -> dict:
        """HTTP headers required when connecting to Deepgram."""
        return {
            "Authorization": f"Token {self.get_api_key()}",
        }


# Singleton — import and use this everywhere
voice_agent = VoiceAgent()
