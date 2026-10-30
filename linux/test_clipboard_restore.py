#!/usr/bin/env python3
"""Check that dictation hands the user's clipboard back intact.

`paste_text` borrows the clipboard to type the transcript. If it only saved
text, a copied image or file would be gone after dictating. Needs a live
Wayland session with wl-clipboard; the keystroke is stubbed out, so nothing
gets typed anywhere. Your current clipboard is put back at the end.

    .venv/bin/python linux/test_clipboard_restore.py
"""

import sys
import zlib
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "windows"))

import paste  # noqa: E402


def _png() -> bytes:
    """A valid 1x1 red PNG, built here so the test ships no fixture."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main():
    # Richest type wins: an image over its HTML/text fallbacks, files over text.
    assert paste._preferred_type(["text/html", "image/png"]) == "image/png"
    assert paste._preferred_type(["text/plain", "text/uri-list"]) == "text/uri-list"
    assert paste._preferred_type(["TEXT", "text/plain;charset=utf-8"]) == "text/plain;charset=utf-8"
    assert paste._preferred_type([]) is None

    if not paste._WAYLAND:
        print("No Wayland session; skipped the live clipboard check.")
        return

    user_clipboard = paste._clip_snapshot()
    paste._tap = lambda *keys: None
    paste._release_user_modifiers = lambda: None
    try:
        image = ("image/png", _png())
        paste._clip_restore(image)
        assert paste._clip_snapshot() == image, "could not seed the clipboard"

        paste.paste_text("dictated text")
        assert paste._clip_snapshot() == image, "dictation lost the copied image"

        paste._clip_restore(("text/plain;charset=utf-8", b"before edit"))
        selection_probe = paste._clip_snapshot()
        paste.restore_clipboard(selection_probe)
        assert paste._clip_read() == "before edit"
    finally:
        paste._clip_restore(user_clipboard)
    print("OK")


if __name__ == "__main__":
    main()
