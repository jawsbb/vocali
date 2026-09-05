"""Desktop notifications — Linux implementation.

pystray's AppIndicator backend has no notification support (`_notify`
raises NotImplementedError), so we call `notify-send` — part of
libnotify, present on every desktop that has a notification daemon.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("vocali.notify")


def send(title: str, message: str, tray=None) -> None:  # noqa: ARG001
    try:
        subprocess.run(
            ["notify-send", "--app-name=Vocali", title, message],
            timeout=5, capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.info("notify-send failed: %s", e)
