"""Per-user single-instance guard — Linux implementation.

Two Vocali processes each open their own /dev/input listener, so one
keypress fires both pipelines and the transcript gets pasted twice.

We bind an abstract unix socket (the leading NUL): the kernel drops the
name when the process dies, so crashes and kills release it for free —
no stale lock file to clean up. The uid is in the name so two users on
the same machine each get their own Vocali.
"""

from __future__ import annotations

import os
import socket
import subprocess

_NAME = f"\0vocali-single-instance-{os.getuid()}"

_held_socket: socket.socket | None = None  # kept alive for the process lifetime


def try_acquire() -> bool:
    """True if we own the name, False if another Vocali holds it."""
    global _held_socket
    if _held_socket is not None:
        return True
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.bind(_NAME)
    except OSError:
        sock.close()
        return False
    _held_socket = sock
    return True


def alert_already_running() -> None:
    try:
        subprocess.run(
            ["notify-send", "--app-name=Vocali", "Vocali is already running",
             "Look for the waveform icon in the system tray."],
            timeout=5, capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass
