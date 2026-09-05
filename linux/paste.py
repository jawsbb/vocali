"""Inject transcribed text into the focused window — Linux implementation.

Same strategy as the Windows port: put the text on the clipboard, then
synthesize Ctrl+V. On Wayland no client may inject keystrokes into another
window, so we go one layer down and create our own virtual keyboard via
`/dev/uinput` — the compositor sees it as an ordinary USB keyboard.

`/dev/uinput` is usually already writable by the logged-in user (systemd
grants a uaccess ACL to the seat owner). If not:

    echo 'KERNEL=="uinput", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-uinput.rules
    sudo udevadm control --reload && sudo udevadm trigger

Clipboard goes through `wl-copy`/`wl-paste` on Wayland and `xclip` on X11
rather than a library, so there's no guessing about which backend pyperclip
picked.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

from evdev import UInput, ecodes

log = logging.getLogger("vocali.paste")

# key_source skips this device so our own Ctrl+V doesn't re-trigger a shortcut.
VIRTUAL_DEVICE_NAME = "Vocali virtual keyboard"

_MODIFIERS = [
    ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
    ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA,
]
_CAPABILITIES = {ecodes.EV_KEY: _MODIFIERS + [ecodes.KEY_V, ecodes.KEY_C,
                                              ecodes.KEY_INSERT]}

# Which chord actually pastes depends on the focused app — terminals ignore
# Ctrl+V and want Ctrl+Shift+V — and Wayland won't tell us which app that is,
# so the user picks in Settings. Keys, not a parser: three real answers.
_PASTE_CHORDS: dict[str, tuple[int, ...]] = {
    "ctrl+v": (ecodes.KEY_LEFTCTRL, ecodes.KEY_V),
    "ctrl+shift+v": (ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT, ecodes.KEY_V),
    "shift+insert": (ecodes.KEY_LEFTSHIFT, ecodes.KEY_INSERT),
}


def _paste_chord() -> tuple[int, ...]:
    """Re-read on every paste so a Settings change applies immediately."""
    import config
    choice = config.Settings.load().paste_shortcut.strip().lower()
    chord = _PASTE_CHORDS.get(choice)
    if chord is None:
        log.warning("Unknown paste shortcut %r; falling back to ctrl+v.", choice)
        return _PASTE_CHORDS["ctrl+v"]
    return chord

_uinput: UInput | None = None
_uinput_lock = threading.Lock()


def _device() -> UInput:
    global _uinput
    with _uinput_lock:
        if _uinput is None:
            _uinput = UInput(_CAPABILITIES, name=VIRTUAL_DEVICE_NAME)
            # A fresh uinput device isn't wired up in the compositor yet;
            # events sent in the first fraction of a second get dropped.
            time.sleep(0.4)
        return _uinput


def _tap(*keys: int) -> None:
    """Press keys in order, release in reverse (a chord)."""
    dev = _device()
    for key in keys:
        dev.write(ecodes.EV_KEY, key, 1)
    dev.syn()
    time.sleep(0.01)
    for key in reversed(keys):
        dev.write(ecodes.EV_KEY, key, 0)
    dev.syn()


def _release_user_modifiers() -> None:
    """Clear modifiers the user may still be holding (e.g. Right Alt during
    a toggle) so our Ctrl+V doesn't turn into Ctrl+Alt+V."""
    dev = _device()
    for key in _MODIFIERS:
        dev.write(ecodes.EV_KEY, key, 0)
    dev.syn()


# ---- clipboard ----

_WAYLAND = bool(os.environ.get("WAYLAND_DISPLAY"))


def _write(cmd: list[str], payload: bytes) -> None:
    """Run a clipboard *writer*.

    stdout/stderr go to /dev/null on purpose: both `wl-copy` and `xclip`
    fork a daemon that owns the selection until someone else claims it, and
    that daemon keeps inherited pipes open — capturing output would block us
    for as long as the clipboard lives.
    """
    try:
        subprocess.run(cmd, input=payload, timeout=3,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Clipboard write via %s failed: %s", cmd[0], e)


def _clip_write(text: str) -> None:
    if _WAYLAND:
        if text:
            _write(["wl-copy", "--type", "text/plain;charset=utf-8"],
                   text.encode("utf-8"))
        else:
            _write(["wl-copy", "--clear"], b"")
        return
    _write(["xclip", "-selection", "clipboard"], text.encode("utf-8"))


def _clip_read() -> str:
    cmd = (["wl-paste", "--no-newline", "--type", "text/plain;charset=utf-8"]
           if _WAYLAND else ["xclip", "-selection", "clipboard", "-o"])
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Clipboard read via %s failed: %s", cmd[0], e)
        return ""
    if result.returncode != 0:
        return ""  # empty clipboard, or it holds something that isn't text
    return result.stdout.decode("utf-8", errors="replace")


# ---- public API (mirrors windows/paste.py) ----

def paste_text(text: str) -> None:
    if not text:
        return
    _clip_write(text)
    # Give the clipboard manager a moment to take ownership.
    time.sleep(0.05)
    _release_user_modifiers()
    time.sleep(0.02)
    _tap(*_paste_chord())


def copy_selection(timeout_ms: int = 300) -> tuple[str, str]:
    """Capture the focused window's selection via Ctrl+C.

    Returns `(selection, original_clipboard)`. Selection is empty when
    nothing was selected. The caller restores the clipboard.
    """
    original = _clip_read()

    # Sentinel so "the selection happens to equal the old clipboard" still
    # reads as a successful copy.
    sentinel = "\x00__vocali_edit_mode_sentinel__\x00"
    _clip_write(sentinel)

    _release_user_modifiers()
    time.sleep(0.02)
    _tap(ecodes.KEY_LEFTCTRL, ecodes.KEY_C)

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        time.sleep(0.02)
        current = _clip_read()
        if current and current != sentinel:
            return current, original
    return "", original


def restore_clipboard(text: str) -> None:
    _clip_write(text)
