"""Small floating overlay shown while recording / transcribing.

Runs a Tk mainloop on a dedicated daemon thread. The main app sends state
changes via thread-safe `after(0, ...)` calls. The overlay is borderless,
always-on-top, and positioned bottom-center on the primary screen.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Literal


State = Literal["idle", "recording", "transcribing", "edit_recording"]


_BG = "#1f1f1f"
_FG_RECORDING = "#e23a3a"
_FG_TRANSCRIBING = "#f0b428"
_FG_EDIT = "#7aa9ff"

_LABEL_FOR: dict[State, tuple[str, str]] = {
    "recording":      ("Recording…",          _FG_RECORDING),
    "transcribing":   ("Transcribing…",       _FG_TRANSCRIBING),
    "edit_recording": ("Listening for edit…", _FG_EDIT),
}


class RecordingOverlay:
    def __init__(self) -> None:
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._dot: tk.Canvas | None = None
        self._dot_id: int | None = None
        self._label: tk.Label | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self) -> None:
        self._thread.start()
        # Wait briefly so first state-change call doesn't race window creation.
        self._ready.wait(timeout=2.0)

    def stop(self) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, self._root.quit)
        except (tk.TclError, RuntimeError):
            pass

    def set_state(self, state: State) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, self._apply_state, state)
        except (tk.TclError, RuntimeError):
            pass

    # ---- runs on the overlay thread ----

    def _run_loop(self) -> None:
        root = tk.Tk()
        root.withdraw()  # hide the implicit root; overlay is a Toplevel
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.92)
        win.configure(bg=_BG)

        # Compose layout: red dot + status label, side by side.
        frame = tk.Frame(win, bg=_BG, padx=12, pady=8)
        frame.pack()
        dot = tk.Canvas(frame, width=14, height=14, bg=_BG, highlightthickness=0)
        dot.pack(side="left", padx=(0, 8))
        dot_id = dot.create_oval(2, 2, 12, 12, fill=_FG_RECORDING, outline="")
        label = tk.Label(
            frame, text="Recording…", fg=_FG_RECORDING, bg=_BG,
            font=("Segoe UI", 10, "bold"),
        )
        label.pack(side="left")

        # Position bottom-center.
        win.update_idletasks()
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        w = win.winfo_width() or 200
        h = win.winfo_height() or 36
        x = (screen_w - w) // 2
        y = screen_h - h - 80
        win.geometry(f"+{x}+{y}")
        win.withdraw()

        self._root = root
        self._dot = dot
        self._dot_id = dot_id
        self._label = label
        self._win = win
        self._ready.set()

        try:
            root.mainloop()
        finally:
            try:
                win.destroy()
                root.destroy()
            except tk.TclError:
                pass

    def _apply_state(self, state: State) -> None:
        if self._win is None or self._label is None or self._dot is None or self._dot_id is None:
            return
        if state == "idle":
            self._win.withdraw()
            return

        labelled = _LABEL_FOR.get(state)
        if labelled is None:
            self._win.withdraw()
            return
        text, color = labelled
        self._label.configure(text=text, fg=color)
        self._dot.itemconfigure(self._dot_id, fill=color)
        self._win.deiconify()
        # Re-assert always-on-top in case another window grabbed it.
        self._win.attributes("-topmost", True)
