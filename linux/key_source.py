"""Global keyboard event source — Linux implementation (evdev).

Reads raw key events straight from `/dev/input/event*`, which is the only
way to see key *releases* system-wide on Wayland: compositors hand
synthetic-shortcut APIs (KGlobalAccel, portals) press events only, and
hold-to-talk needs both edges.

Keyboards are re-scanned every few seconds, so one that sleeps, is replugged,
or arrives through a KVM switch starts working again on its own.

Requires read access to the input devices:

    sudo usermod -aG input $USER    # then log out and back in

Events handed to the callback mimic the `keyboard` library's shape that
`hotkeys.py` expects: `.name` (e.g. "right alt") and `.event_type`
("down" / "up").
"""

from __future__ import annotations

import logging
import selectors
import threading
import time
from typing import Callable

from evdev import InputDevice, ecodes, list_devices

log = logging.getLogger("vocali.key_source")

# Our own synthetic paste keystrokes come from a uinput device (see paste.py).
# Reading them back would re-trigger the very shortcut that produced them.
from paste import VIRTUAL_DEVICE_NAME

# How often to look for keyboards that appeared while we were running.
RESCAN_INTERVAL_S = 5.0


# evdev spells modifiers as LEFTCTRL/RIGHTALT/…; hotkeys.ALIASES speaks
# "left ctrl" / "right alt". Everything else maps by stripping "KEY_".
_RENAMED = {
    "leftctrl": "left ctrl",
    "rightctrl": "right ctrl",
    "leftshift": "left shift",
    "rightshift": "right shift",
    "leftalt": "left alt",
    "rightalt": "right alt",
    "leftmeta": "left windows",
    "rightmeta": "right windows",
    "capslock": "caps lock",
    "pageup": "page up",
    "pagedown": "page down",
    "kpenter": "enter",
}


def _key_name(code: int) -> str:
    name = ecodes.KEY.get(code)
    if isinstance(name, (list, tuple)):
        name = name[0]
    if not name or not name.startswith("KEY_"):
        return ""
    short = name[4:].lower()
    return _RENAMED.get(short, short)


def _is_keyboard(dev: InputDevice) -> bool:
    if dev.name == VIRTUAL_DEVICE_NAME:
        return False
    keys = set(dev.capabilities().get(ecodes.EV_KEY, ()))
    # A real keyboard has letters, space and a control key. Mice and
    # power buttons advertise EV_KEY too, hence the triple check.
    return {ecodes.KEY_A, ecodes.KEY_SPACE, ecodes.KEY_LEFTCTRL} <= keys


class _Event:
    __slots__ = ("name", "event_type")

    def __init__(self, name: str, event_type: str) -> None:
        self.name = name
        self.event_type = event_type


def _open_keyboards() -> list[InputDevice]:
    devices = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue  # unreadable device — permissions, or it just vanished
        if _is_keyboard(dev):
            devices.append(dev)
        else:
            dev.close()
    return devices


def hook(callback: Callable[[object], None]) -> Callable[[], None]:
    """Start listening on every keyboard. Returns the unhook callable."""
    devices: dict[str, InputDevice] = {}
    selector = selectors.DefaultSelector()
    stop = threading.Event()

    def adopt_new_keyboards() -> None:
        """Pick up keyboards that appeared since the last look.

        A wireless keyboard that sleeps, a USB one replugged, a KVM switch
        flipped — each comes back as a *new* /dev/input node. Enumerating
        only at startup would leave dictation silently dead until the app
        was restarted, which is the kind of failure nobody reports as a bug
        because it just looks like the hotkey stopped working.
        """
        for dev in _open_keyboards():
            if dev.path in devices:
                dev.close()
                continue
            devices[dev.path] = dev
            selector.register(dev, selectors.EVENT_READ)
            log.info("Listening on keyboard: %s (%s)", dev.name, dev.path)

    def drop(dev: InputDevice) -> None:
        selector.unregister(dev)
        devices.pop(dev.path, None)
        try:
            dev.close()
        except OSError:
            pass
        log.info("Keyboard went away: %s", dev.path)

    adopt_new_keyboards()
    if not devices:
        raise RuntimeError(
            "No readable keyboard found under /dev/input. Add yourself to the "
            "'input' group (sudo usermod -aG input $USER) and log back in."
        )

    def loop() -> None:
        next_scan = time.monotonic() + RESCAN_INTERVAL_S
        while not stop.is_set():
            for key, _mask in selector.select(timeout=0.5):
                dev = key.fileobj
                try:
                    events = list(dev.read())
                except OSError:
                    drop(dev)
                    continue
                for event in events:
                    if event.type != ecodes.EV_KEY or event.value == 2:
                        continue  # value 2 == autorepeat, not a new edge
                    name = _key_name(event.code)
                    if not name:
                        continue
                    callback(_Event(name, "down" if event.value == 1 else "up"))

            if time.monotonic() >= next_scan:
                next_scan = time.monotonic() + RESCAN_INTERVAL_S
                try:
                    adopt_new_keyboards()
                except Exception as e:
                    log.info("Keyboard rescan failed: %s", e)

    thread = threading.Thread(target=loop, name="vocali-keys", daemon=True)
    thread.start()

    def unhook() -> None:
        stop.set()
        thread.join(timeout=1.5)
        selector.close()
        for dev in devices.values():
            try:
                dev.close()
            except OSError:
                pass
        devices.clear()

    return unhook
