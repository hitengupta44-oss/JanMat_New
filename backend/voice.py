"""
Voice layer via Sarvam AI:
  - transcribe_audio(): user's spoken question -> text (Saaras v3 STT)
  - synthesize_speech(): the chatbot's answer -> spoken audio (Bulbul v3 TTS)

Docs: https://docs.sarvam.ai/api-reference/introduction
Both endpoints are synchronous REST calls suitable for short clips
(STT: files under ~30s; TTS: text under ~2500 chars per call — chunk longer
answers before calling synthesize_speech if needed).
"""
import base64
import logging
from typing import Optional

import requests

from config import (
    SARVAM_API_KEY,
    SARVAM_STT_MODEL,
    SARVAM_TTS_MODEL,
    SARVAM_DEFAULT_SPEAKER,
    SARVAM_DEFAULT_LANGUAGE,
)

logger = logging.getLogger("janmat.voice")

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"


def _headers() -> dict:
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set")
    return {"api-subscription-key": SARVAM_API_KEY}


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav",
                      language_code: str = "unknown", mode: str = "transcribe") -> dict:
    """
    Sends an audio clip to Sarvam's /speech-to-text (Saaras v3).
    language_code="unknown" lets Sarvam auto-detect the spoken Indian
    language; pass a BCP-47 code (e.g. "hi-IN") if you already know it.

    Returns: {"transcript": str, "language_code": str}
    """
    files = {"file": (filename, audio_bytes)}
    data = {"model": SARVAM_STT_MODEL, "language_code": language_code, "mode": mode}
    resp = requests.post(STT_URL, headers=_headers(), files=files, data=data, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return {
        "transcript": body.get("transcript", ""),
        "language_code": body.get("language_code", language_code),
    }


def synthesize_speech(text: str, language_code: str = SARVAM_DEFAULT_LANGUAGE,
                       speaker: str = SARVAM_DEFAULT_SPEAKER, pace: float = 1.0) -> bytes:
    """
    Calls Sarvam's /text-to-speech (Bulbul v3). The REST endpoint accepts up
    to ~2500 characters per call — split longer answers into chunks and
    concatenate the resulting WAV bytes client-side if needed.

    Returns raw WAV audio bytes (decoded from the base64 the API returns).
    """
    payload = {
        "text": text[:2500],
        "target_language_code": language_code,
        "speaker": speaker,
        "pace": pace,
        "model": SARVAM_TTS_MODEL,
    }
    headers = {**_headers(), "Content-Type": "application/json"}
    resp = requests.post(TTS_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    audios = body.get("audios", [])
    if not audios:
        raise RuntimeError(f"Sarvam TTS returned no audio: {body}")
    return base64.b64decode(audios[0])
