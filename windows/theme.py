"""Windows 11-style theming via sv-ttk, with system-mode detection.

Centralised so every Tk root in the app (Settings, recording overlay,
future windows) gets the same visual treatment. We detect the user's
Windows "Apps mode" from the registry and apply the matching sv-ttk
theme — this is the same signal File Explorer uses, so Vocali matches
the rest of the OS.
"""

from __future__ import annotations

import logging
from typing import Literal

log = logging.getLogger("vocali.theme")


Mode = Literal["light", "dark"]


def detect_system_mode() -> Mode:
    """Read HKCU\\…\\Personalize\\AppsUseLightTheme. Defaults to dark on
    any failure (Windows 11 default-feel)."""
    try:
        import winreg
    except ImportError:
        return "dark"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0,
            winreg.KEY_READ,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) == 1 else "dark"
        finally:
            winreg.CloseKey(key)
    except (FileNotFoundError, OSError):
        return "dark"


def apply(root, mode: Mode | None = None) -> Mode:
    """Apply the sv-ttk theme. Returns the mode actually used."""
    chosen: Mode = mode or detect_system_mode()
    try:
        import sv_ttk
        sv_ttk.set_theme(chosen, root=root)
    except Exception as e:
        # Theming is purely cosmetic — never crash the UI for a missing theme.
        log.warning("Failed to apply sv-ttk theme: %s", e)
    return chosen


# Accent colors used by overlays and other plain Tk widgets that aren't
# automatically themed by sv-ttk (e.g. tk.Canvas, tk.Toplevel backgrounds).
DARK_PALETTE = {
    "bg":        "#1c1c1c",
    "surface":   "#2b2b2b",
    "ink":       "#f4f1ea",
    "ink_dim":   "#a8a499",
    "accent":    "#7aa9ff",
    "recording": "#e23a3a",
    "transcribing": "#f0b428",
}

LIGHT_PALETTE = {
    "bg":        "#fafafa",
    "surface":   "#ffffff",
    "ink":       "#1a1a17",
    "ink_dim":   "#6b6b60",
    "accent":    "#2b2bd1",
    "recording": "#dc2626",
    "transcribing": "#d97706",
}


def palette(mode: Mode | None = None) -> dict[str, str]:
    chosen = mode or detect_system_mode()
    return DARK_PALETTE if chosen == "dark" else LIGHT_PALETTE
