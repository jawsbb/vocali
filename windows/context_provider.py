"""Lightweight foreground-window context for the LLM cleanup prompt.

The Mac app reads the focused app's accessibility tree to feed the cleanup
prompt with surrounding text — recipient names in an email, terminal prompt,
etc. Doing the same on Windows requires UI Automation, which is heavy.

This module returns a much smaller MVP: foreground window title + executable
name + window class. That alone helps the cleanup model spell names that
appear in window titles (e.g. an email recipient shown in the tab title) and
distinguish "writing in chat" from "writing in IDE" by the executable name.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _foreground_window() -> int:
    return user32.GetForegroundWindow()


def _window_text(hwnd: int) -> str:
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or ""


def _window_class(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value or ""


def _window_process_name(hwnd: int) -> str:
    if not hwnd:
        return ""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        # QueryFullProcessImageNameW is the modern, non-deprecated path
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def context_summary() -> str:
    """Return a single-line, prompt-friendly description of the focused app.

    Empty string if nothing useful is available.
    """
    hwnd = _foreground_window()
    if not hwnd:
        return ""
    title = _window_text(hwnd).strip()
    process = _window_process_name(hwnd).strip()
    cls = _window_class(hwnd).strip()

    parts: list[str] = []
    if process:
        parts.append(f"app={process}")
    if title:
        # Trim absurdly long titles to keep the prompt tight
        parts.append(f'title="{title[:200]}"')
    if cls and cls.lower() not in {"window", "shellexperiencehost", "applicationframewindow"}:
        parts.append(f"class={cls}")
    return "; ".join(parts)
