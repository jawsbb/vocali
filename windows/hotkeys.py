"""Global hotkey handling: hold-to-talk and tap-to-toggle.

We hook every keyboard event with the `keyboard` library and maintain our own
set of currently-pressed key names. This avoids `keyboard.is_pressed`, whose
hotkey parser rejects multi-word names like "right alt" on layouts where the
key is reported as "alt gr" (AZERTY) or "right ctrl" (some installations).

Combo strings are written like "right alt" or "ctrl+right alt". Each token
expands to a set of acceptable key-name aliases — so "right alt" matches both
literal "right alt" and the "alt gr" reported on French keyboards, and "ctrl"
matches either left or right control.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable


# Map a canonical token to the set of `event.name` values that satisfy it.
ALIASES: dict[str, set[str]] = {
    "ctrl":        {"ctrl", "control", "left ctrl", "right ctrl",
                    "left control", "right control"},
    "control":     {"ctrl", "control", "left ctrl", "right ctrl",
                    "left control", "right control"},
    "left ctrl":   {"left ctrl", "left control"},
    "right ctrl":  {"right ctrl", "right control"},
    "alt":         {"alt", "left alt", "right alt", "alt gr", "altgr"},
    "left alt":    {"left alt", "alt"},
    "right alt":   {"right alt", "alt gr", "altgr"},
    "alt gr":      {"alt gr", "altgr", "right alt"},
    "altgr":       {"alt gr", "altgr", "right alt"},
    "shift":       {"shift", "left shift", "right shift"},
    "left shift":  {"left shift"},
    "right shift": {"right shift"},
    "win":         {"windows", "left windows", "right windows", "left win", "right win"},
    "windows":     {"windows", "left windows", "right windows", "left win", "right win"},
}


def _resolve(token: str) -> frozenset[str]:
    t = token.strip().lower()
    if not t:
        return frozenset()
    return frozenset(ALIASES.get(t, {t}))


def _parse(combo: str) -> tuple[frozenset[str], ...]:
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    return tuple(_resolve(p) for p in parts)


def _all_satisfied(combo: tuple[frozenset[str], ...], pressed: set[str]) -> bool:
    if not combo:
        return False
    return all(any(name in pressed for name in token) for token in combo)


def _any_token_matches(combo: tuple[frozenset[str], ...], key_name: str) -> bool:
    return any(key_name in token for token in combo)


class HotkeyManager:
    """Tracks hold-to-talk and tap-to-toggle shortcuts.

    - on_hold_start fires once when every key in `hold_combo` is down.
    - on_hold_end fires when any of those keys is released.
    - on_toggle fires on the trailing edge of a clean press-release of every
      key in `toggle_combo`. Suppressed while a hold session is active.
    """

    def __init__(
        self,
        hold_combo: str,
        toggle_combo: str | None,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[], None],
        on_toggle: Callable[[], None] | None = None,
    ) -> None:
        self._hold = _parse(hold_combo)
        self._toggle = _parse(toggle_combo) if toggle_combo else tuple()
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end
        self._on_toggle = on_toggle
        self._pressed: set[str] = set()
        self._holding = False
        self._toggle_armed = False
        self._lock = threading.Lock()
        self._hook = None

    def start(self) -> None:
        if self._hook is not None:
            return
        import keyboard
        self._hook = keyboard.hook(self._on_event)

    def stop(self) -> None:
        if self._hook is None:
            return
        import keyboard
        keyboard.unhook(self._hook)
        self._hook = None
        with self._lock:
            self._pressed.clear()
            if self._holding:
                self._holding = False
                _safe_call(self._on_hold_end)

    def update(self, hold_combo: str, toggle_combo: str | None) -> None:
        was_running = self._hook is not None
        self.stop()
        self._hold = _parse(hold_combo)
        self._toggle = _parse(toggle_combo) if toggle_combo else tuple()
        if was_running:
            self.start()

    # `keyboard.hook` callback. Runs on the library's listener thread.
    def _on_event(self, event) -> None:
        if event.event_type not in ("down", "up"):
            return
        name = (event.name or "").lower()
        if not name:
            return

        with self._lock:
            if event.event_type == "down":
                self._pressed.add(name)
            else:
                self._pressed.discard(name)

            hold_now = _all_satisfied(self._hold, self._pressed)
            if hold_now and not self._holding:
                self._holding = True
                self._toggle_armed = False
                _safe_call(self._on_hold_start)
                return
            if not hold_now and self._holding:
                self._holding = False
                _safe_call(self._on_hold_end)
                return

            if self._toggle and self._on_toggle and not self._holding:
                toggle_now = _all_satisfied(self._toggle, self._pressed)
                if toggle_now and not self._toggle_armed:
                    self._toggle_armed = True
                elif (
                    not toggle_now
                    and self._toggle_armed
                    and event.event_type == "up"
                    and _any_token_matches(self._toggle, name)
                ):
                    self._toggle_armed = False
                    _safe_call(self._on_toggle)


def _safe_call(fn: Callable[[], None] | None) -> None:
    if fn is None:
        return
    try:
        fn()
    except Exception:
        pass
