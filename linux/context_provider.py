"""Foreground-window context — Linux implementation.

Returns nothing. On Wayland there is no way for an ordinary client to read
the focused window's title, let alone the text around the cursor: that is
the whole point of the security model. The Windows port's UI Automation
walk has no equivalent that works out of the box.

AT-SPI (the accessibility bus) is the closest thing, but on a stock Fedora
/ KDE install it only exposes the desktop shell's own helpers — Qt and GTK
apps register with it only when accessibility is switched on system-wide.
Not worth making the dictation pipeline depend on.

So `use_window_context` is a no-op here: cleanup runs without context.

ponytail: upgrade path is AT-SPI via `gi.repository.Atspi`, gated on the
user having enabled accessibility (`gsettings set org.gnome.desktop.interface
toolkit-accessibility true` plus `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`).
"""

from __future__ import annotations


def context_summary(use_uia: bool = True) -> str:  # noqa: ARG001
    return ""
