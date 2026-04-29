"""Foreground-window context for the LLM cleanup prompt.

Two layers, combined into a single ``context_summary()`` string:

1. Cheap Win32 metadata (~5 ms): foreground window title + executable name
   + window class. Always available.
2. Optional UI Automation accessibility text (50–800 ms): walks the UIA
   tree from the focused element up to the top-level window, collecting
   visible labels and text values from ancestors and the focused element's
   immediate siblings. This is what gives the cleanup model surrounding
   text — recipient names, email subject, chat thread, IDE breadcrumbs.

The UIA layer is bounded by a hard deadline and a max-elements cap so a
slow or pathological app can't stall the dictation pipeline.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import time


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# UIA tuning. UIA property reads are ~50 ms each in the worst case; these
# limits keep the total bounded even in deeply-nested apps.
UIA_DEADLINE_S = 0.9
UIA_MAX_ANCESTORS = 8
UIA_MAX_SIBLINGS = 12
UIA_MAX_TEXT_PER_ELEMENT = 200
UIA_MAX_TOTAL_CHARS = 600
UIA_BORING_NAMES = {
    "", "pane", "window", "document", "form",
    "shellexperiencehost", "applicationframewindow",
}


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


def _basic_summary() -> str:
    """Cheap Win32 layer: process name + window title."""
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
        parts.append(f'title="{title[:200]}"')
    if cls and cls.lower() not in {"window", "shellexperiencehost", "applicationframewindow"}:
        parts.append(f"class={cls}")
    return "; ".join(parts)


def _safe_get(prop_callable, default: str = "") -> str:
    try:
        v = prop_callable()
    except Exception:
        return default
    if v is None:
        return default
    s = str(v).strip()
    return s


def _read_text(elem) -> str:
    """Read whatever readable text we can off a UIA element. Best-effort."""
    pieces: list[str] = []
    name = _safe_get(lambda: elem.Name)
    if name:
        pieces.append(name)

    # ValuePattern.Value — text-edit fields, comboboxes, address bars.
    try:
        if elem.IsValuePatternAvailable():
            val = _safe_get(lambda: elem.GetValuePattern().Value)
            if val and val not in pieces:
                pieces.append(val)
    except Exception:
        pass

    # LegacyIAccessiblePattern.Value — older Win32 controls (Notepad, Edge legacy).
    try:
        if elem.IsLegacyIAccessiblePatternAvailable():
            val = _safe_get(lambda: elem.GetLegacyIAccessiblePattern().Value)
            if val and val not in pieces:
                pieces.append(val)
    except Exception:
        pass

    text = " · ".join(p for p in pieces if p)
    if len(text) > UIA_MAX_TEXT_PER_ELEMENT:
        text = text[:UIA_MAX_TEXT_PER_ELEMENT].rstrip() + "…"
    return text


def _is_useful(text: str) -> bool:
    if not text:
        return False
    return text.strip().lower() not in UIA_BORING_NAMES


def _accessibility_text(deadline_at: float) -> str:
    """UIA layer: collect text from focused element + ancestors + siblings.

    Bounded by ``deadline_at`` (a ``time.monotonic()`` value). Returns empty
    string on any failure, including "we ran out of time".
    """
    try:
        import uiautomation as auto
    except Exception:
        return ""

    if time.monotonic() >= deadline_at:
        return ""

    try:
        focused = auto.GetFocusedControl()
    except Exception:
        return ""
    if focused is None:
        return ""

    seen: set[str] = set()
    collected: list[str] = []

    def add(text: str) -> None:
        if not _is_useful(text):
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        collected.append(text)

    # Focused element itself.
    add(_read_text(focused))

    # Walk up the ancestor chain, capturing labels and any text content.
    parent = focused
    for _ in range(UIA_MAX_ANCESTORS):
        if time.monotonic() >= deadline_at:
            break
        try:
            parent = parent.GetParentControl()
        except Exception:
            break
        if parent is None:
            break
        add(_read_text(parent))

    # Immediate siblings of the focus — typically the labels and adjacent
    # fields in the same form (To:, Subject:, etc.).
    if time.monotonic() < deadline_at:
        try:
            sibling_parent = focused.GetParentControl()
        except Exception:
            sibling_parent = None
        if sibling_parent is not None:
            count = 0
            try:
                for child in sibling_parent.GetChildren():
                    if time.monotonic() >= deadline_at or count >= UIA_MAX_SIBLINGS:
                        break
                    count += 1
                    if child == focused:
                        continue
                    add(_read_text(child))
            except Exception:
                pass

    if not collected:
        return ""

    joined = " | ".join(collected)
    if len(joined) > UIA_MAX_TOTAL_CHARS:
        joined = joined[:UIA_MAX_TOTAL_CHARS].rstrip() + "…"
    return joined


def context_summary(use_uia: bool = True) -> str:
    """Return a single-line, prompt-friendly description of the focused app.

    Empty string if nothing useful is available. ``use_uia=False`` skips the
    expensive accessibility-tree walk and returns only Win32 metadata.
    """
    base = _basic_summary()
    if not use_uia:
        return base

    deadline = time.monotonic() + UIA_DEADLINE_S
    accessibility = _accessibility_text(deadline)

    if accessibility:
        return f"{base}; nearby={accessibility}" if base else f"nearby={accessibility}"
    return base
