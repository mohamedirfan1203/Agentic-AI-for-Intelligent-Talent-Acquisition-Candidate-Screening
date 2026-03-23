"""
Voice Agent Configuration
==========================
Centralised Deepgram Voice-Agent settings template.
"""

AGENT_SETTINGS: dict = {
    "type": "Settings",
    "audio": {
        "input": {
            "encoding": "linear16",
            "sample_rate": 48000,
        },
        "output": {
            "encoding": "linear16",
            "sample_rate": 24000,
            "container": "none",
        },
    },
    "agent": {
        "language": "en",
        "speak": {
            "provider": {
                "type": "deepgram",
                "model": "aura-2-vesta-en",
            },
        },
        "listen": {
            "provider": {
                "type": "deepgram",
                "version": "v2",
                "model": "flux-general-en",
            },
        },
        "think": {
            "provider": {
                "type": "google",
                "model": "gemini-2.5-flash",
            },
            "prompt": "",
        },
        "greeting": "",
    },
}
