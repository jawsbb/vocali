"""Run-on-login — Linux implementation (XDG autostart).

Writes `~/.config/autostart/vocali.desktop`, which every desktop
environment reads. Per-user, no root needed.

`sys.executable` is baked into Exec= so a virtualenv install keeps
working after login.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

_VALUE_NAME = "vocali"


def _autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart" / f"{_VALUE_NAME}.desktop"


def _resolve_command() -> str:
    launcher = Path(__file__).resolve().parent / "vocali"
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(launcher))}"


def is_enabled() -> bool:
    return _autostart_path().exists()


def enable() -> None:
    path = _autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Vocali\n"
        "Comment=Voice-to-text dictation\n"
        f"Exec={_resolve_command()}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


def disable() -> None:
    _autostart_path().unlink(missing_ok=True)


def set_enabled(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()


def current_command() -> str | None:
    """Return the registered Exec= line, or None if auto-start is off."""
    try:
        for line in _autostart_path().read_text(encoding="utf-8").splitlines():
            if line.startswith("Exec="):
                return line[len("Exec="):] or None
    except OSError:
        return None
    return None
