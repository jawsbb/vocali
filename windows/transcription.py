"""Groq Whisper transcription client. Mirrors the Mac app's behavior."""

from __future__ import annotations

import json

import requests


HALLUCINATION_PHRASES = {
    "thank you",
    "thank you for watching",
    "thank you very much",
    "thank you so much",
    "thanks for watching",
    "please subscribe",
    "like and subscribe",
    "subtitles by",
    "subtitles by the amara.org community",
    "you",
}
HALLUCINATION_NO_SPEECH_THRESHOLD = 0.1
TIMEOUT_SECONDS = 20.0


class TranscriptionError(Exception):
    pass


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise TranscriptionError("Provider URL is empty.")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise TranscriptionError("Provider URL must use http or https.")
    return base


def validate_api_key(api_key: str, base_url: str = "https://api.groq.com/openai/v1") -> bool:
    key = (api_key or "").strip()
    if not key:
        return False
    try:
        url = _normalize_base_url(base_url) + "/models"
        resp = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _is_hallucination(text: str, payload: dict) -> bool:
    normalized = text.strip().strip(".,!?;:'\"").lower()
    if normalized not in HALLUCINATION_PHRASES:
        return False
    segments = payload.get("segments") or []
    if not segments:
        return False
    no_speech = segments[0].get("no_speech_prob")
    if not isinstance(no_speech, (int, float)):
        return False
    return no_speech >= HALLUCINATION_NO_SPEECH_THRESHOLD


def transcribe(
    wav_bytes: bytes,
    api_key: str,
    base_url: str = "https://api.groq.com/openai/v1",
    model: str = "whisper-large-v3",
    language: str | None = None,
) -> str:
    if not wav_bytes:
        return ""
    base = _normalize_base_url(base_url)
    url = f"{base}/audio/transcriptions"

    files = {"file": ("recording.wav", wav_bytes, "audio/wav")}
    data: dict[str, str] = {
        "model": (model or "whisper-large-v3").strip() or "whisper-large-v3",
        "response_format": "verbose_json",
    }
    lang = (language or "").strip()
    if lang:
        data["language"] = lang

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        raise TranscriptionError(f"Transcription timed out after {int(TIMEOUT_SECONDS)}s")
    except requests.RequestException as e:
        raise TranscriptionError(f"Upload failed: {e}")

    if resp.status_code != 200:
        raise TranscriptionError(f"Status {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except json.JSONDecodeError:
        text = resp.text.replace("\n", " ").strip()
        if not text:
            raise TranscriptionError("Invalid response")
        return text

    text = payload.get("text", "")
    if not isinstance(text, str):
        raise TranscriptionError("Invalid response payload")
    if _is_hallucination(text, payload):
        return ""
    return text
