"""Run-on-login via the per-user Windows Run registry key.

Writes/removes a value under
`HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`.

Per-user (not per-machine) so it never needs admin rights.

Two run modes:
- Frozen (PyInstaller-bundled): the value is the path to Vocali.exe.
- Source: the value is `pythonw.exe` + the absolute path of vocali.py,
  using `pythonw` (no console) instead of `python` so login doesn't
  flash a black box.
"""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Vocali"


def _quote(p: str | Path) -> str:
    return f'"{p}"'


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _resolve_command() -> str:
    """The command line that should run Vocali on login."""
    if _is_frozen():
        return _quote(sys.executable)

    script = Path(__file__).resolve().parent / "vocali.py"
    # Prefer pythonw.exe so login doesn't flash a console window.
    py_dir = Path(sys.executable).resolve().parent
    pyw = py_dir / "pythonw.exe"
    runner = pyw if pyw.exists() else Path(sys.executable)
    return f"{_quote(runner)} {_quote(script)}"


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    cmd = _resolve_command()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, cmd)


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        return
    except OSError:
        return


def set_enabled(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()


def current_command() -> str | None:
    """Return the registered command, or None if auto-start is off."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return value or None
    except (FileNotFoundError, OSError):
        return None
