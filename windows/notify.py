"""Desktop notifications — Windows implementation.

Goes through the tray icon, which owns the toast on Windows. Linux
overrides this module with a `notify-send` call, because pystray's
AppIndicator backend raises NotImplementedError for notifications.
"""

from __future__ import annotations

import logging

log = logging.getLogger("vocali.notify")


def send(title: str, message: str, tray=None) -> None:
    if tray is None:
        return
    try:
        tray.notify(message, title)
    except Exception as e:
        # Toasts fail on some Windows configurations (Focus Assist, missing
        # shell notification area). Never let that break the caller.
        log.info("Notification failed: %s", e)
