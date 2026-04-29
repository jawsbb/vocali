"""Inject transcribed text into the focused window.

Strategy: copy text to the clipboard, then synthesize Ctrl+V via the Win32
SendInput API. SendInput is preferred over the `keyboard` library here because
it always targets the foreground window and does not interact with our hook.

Modifier keys held down by the user (e.g. Right Alt because they're toggling
with Ctrl+RAlt) would cause Ctrl+V to combine with them, so we briefly release
all common modifiers via virtual key-up events before the paste, then leave
them alone (the user is responsible for releasing them).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

import pyperclip


user32 = ctypes.WinDLL("user32", use_last_error=True)


# https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-input
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LMENU = 0xA4   # Left Alt
VK_RMENU = 0xA5   # Right Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_CONTROL = 0x11
VK_V = 0x56


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


def _key_event(vk: int, key_up: bool) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if key_up else 0,
        time=0,
        dwExtraInfo=None,
    )
    return inp


def _send(events: list[_INPUT]) -> None:
    n = len(events)
    arr = (_INPUT * n)(*events)
    user32.SendInput(n, arr, ctypes.sizeof(_INPUT))


def _release_user_modifiers() -> None:
    """Send key-up events for any modifier the user might be holding.

    Sending KEYUP for a key that wasn't actually down is a no-op on Windows.
    """
    for vk in (VK_LCONTROL, VK_RCONTROL, VK_LSHIFT, VK_RSHIFT,
               VK_LMENU, VK_RMENU, VK_LWIN, VK_RWIN):
        _send([_key_event(vk, True)])


def paste_text(text: str) -> None:
    if not text:
        return
    pyperclip.copy(text)
    # Give the clipboard a moment to settle before sending the paste shortcut.
    time.sleep(0.03)
    _release_user_modifiers()
    time.sleep(0.01)
    _send([
        _key_event(VK_CONTROL, False),
        _key_event(VK_V, False),
        _key_event(VK_V, True),
        _key_event(VK_CONTROL, True),
    ])
