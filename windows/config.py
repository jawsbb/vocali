"""Persisted settings + secure API-key storage.

Plain settings live in `%APPDATA%\\Vocali\\settings.json`. The Groq API key
goes into Windows Credential Manager via `keyring`, never the JSON file.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

import keyring


KEYRING_SERVICE = "Vocali"
KEYRING_USER = "groq-api-key"


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = Path(base) / "Vocali"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return _config_dir() / "settings.json"


@dataclass
class Settings:
    base_url: str = "https://api.groq.com/openai/v1"
    transcription_model: str = "whisper-large-v3"
    primary_llm_model: str = ""
    fallback_llm_model: str = ""
    language: str = ""
    output_language: str = ""
    cleanup_enabled: bool = True
    custom_vocabulary: str = ""
    custom_system_prompt: str = ""
    hold_shortcut: str = "right alt"
    toggle_shortcut: str = "ctrl+right alt"
    play_sounds: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        path = _config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    def save(self) -> None:
        path = _config_path()
        with _save_lock:
            path.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )


_save_lock = threading.Lock()


def get_api_key() -> str:
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except keyring.errors.KeyringError:
        return ""
    return (value or "").strip()


def set_api_key(value: str) -> None:
    value = (value or "").strip()
    if value:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, value)
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except keyring.errors.PasswordDeleteError:
            pass
