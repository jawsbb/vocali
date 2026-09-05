"""Global keyboard event source — Windows implementation.

`hook(callback)` starts a system-wide key listener and returns a callable
that stops it. Events passed to `callback` have `.name` (lowercase key
name, e.g. "right alt") and `.event_type` ("down" / "up").

Linux overrides this module with an evdev-based source; see `linux/`.
"""

from __future__ import annotations

from typing import Callable


def hook(callback: Callable[[object], None]) -> Callable[[], None]:
    import keyboard
    handle = keyboard.hook(callback)

    def unhook() -> None:
        keyboard.unhook(handle)

    return unhook
