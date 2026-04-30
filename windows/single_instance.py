"""Per-user single-instance guard via a named Windows mutex.

When the user accidentally launches Vocali twice (download-clicked the
.exe a few times, has run-on-login plus a manual launch, kept an old
instance running, etc.), each process installs its own global keyboard
hook. Pressing the dictation shortcut then fires every instance in
parallel: each one records, transcribes, and pastes — so the transcript
ends up duplicated N times in the focused field.

We grab a session-local named mutex on startup. If another Vocali in the
same user session already holds it, this process should bail out before
touching any global state. Mutex is held implicitly until the OS reaps
the process, so crashes and forced kills release it automatically.
"""

from __future__ import annotations

import ctypes


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ERROR_ALREADY_EXISTS = 183

# "Local\" namespace = the current Windows session only. Two users on the
# same machine each get their own Vocali.
_MUTEX_NAME = r"Local\Vocali-SingleInstance-Mutex-v1"


_held_handle = None  # kept alive for the lifetime of the process


def try_acquire() -> bool:
    """Return True if we own the mutex, False if another Vocali holds it.

    Errors creating the mutex (rare — sandboxed environments, etc.) fall
    through to True so we don't lock the user out of their own app.
    """
    global _held_handle
    if _held_handle is not None:
        return True

    handle = _kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if not handle:
        return True

    last = ctypes.get_last_error()
    if last == _ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return False

    _held_handle = handle
    return True
