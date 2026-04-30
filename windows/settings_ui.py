"""Tkinter settings window. Run on its own thread when opened from the tray."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

import auto_start
import config
import transcription


class SettingsWindow:
    def __init__(
        self,
        settings: config.Settings,
        on_save: Callable[[config.Settings], None],
    ) -> None:
        self._settings = settings
        self._on_save = on_save

        self._root = tk.Tk()
        self._root.title("Vocali Settings")
        self._root.geometry("560x640")
        self._root.minsize(540, 600)

        self._api_key_var = tk.StringVar(value=config.get_api_key())
        self._base_url_var = tk.StringVar(value=settings.base_url)
        self._transcription_model_var = tk.StringVar(value=settings.transcription_model)
        self._primary_model_var = tk.StringVar(value=settings.primary_llm_model)
        self._fallback_model_var = tk.StringVar(value=settings.fallback_llm_model)
        self._language_var = tk.StringVar(value=settings.language)
        self._output_language_var = tk.StringVar(value=settings.output_language)
        self._cleanup_var = tk.BooleanVar(value=settings.cleanup_enabled)
        self._hold_var = tk.StringVar(value=settings.hold_shortcut)
        self._toggle_var = tk.StringVar(value=settings.toggle_shortcut)
        self._edit_var = tk.StringVar(value=settings.edit_shortcut)
        self._edit_enabled_var = tk.BooleanVar(value=settings.edit_mode_enabled)
        self._show_overlay_var = tk.BooleanVar(value=settings.show_overlay)
        self._use_context_var = tk.BooleanVar(value=settings.use_window_context)
        # Source of truth for the "auto-start" checkbox is the registry, not
        # settings.json — the user can toggle the registry independently
        # (msconfig, Task Manager, etc.) and we want the UI to reflect that.
        self._auto_start_var = tk.BooleanVar(value=auto_start.is_enabled())
        self._check_updates_var = tk.BooleanVar(value=settings.check_updates)

        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        nb = ttk.Notebook(self._root)
        nb.pack(fill="both", expand=True, **pad)

        # --- General tab ---
        general = ttk.Frame(nb)
        nb.add(general, text="General")

        # API key gets a custom row with Show / Paste / Test buttons. The
        # plain `_row` helper doesn't cut it because we need a reference to
        # the Entry widget (to flip `show` for the masking toggle and to
        # read its value directly when StringVar is desynced — which can
        # happen when Tk runs in a non-main thread alongside the global
        # keyboard hook).
        ttk.Label(general, text="Groq API key").grid(row=0, column=0, sticky="w", padx=12, pady=6)
        api_frame = ttk.Frame(general)
        api_frame.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        self._api_key_entry = ttk.Entry(
            api_frame, textvariable=self._api_key_var, show="*"
        )
        self._api_key_entry.pack(side="left", fill="x", expand=True)
        self._show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            api_frame, text="Show", variable=self._show_key_var,
            command=self._toggle_api_key_visibility,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(api_frame, text="Paste", command=self._paste_api_key).pack(side="left", padx=(4, 0))
        ttk.Button(api_frame, text="Test", command=self._test_api_key).pack(side="left", padx=(4, 0))

        self._row(general, 1, "Provider base URL", self._base_url_var, width=48)
        self._row(general, 2, "Transcription model", self._transcription_model_var, width=48)
        self._row(general, 3, "Spoken language (ISO, optional)", self._language_var, width=20)

        cleanup_frame = ttk.LabelFrame(general, text="Post-processing")
        cleanup_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Checkbutton(
            cleanup_frame,
            text="Enable LLM cleanup (filler removal, punctuation, etc.)",
            variable=self._cleanup_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6, columnspan=2)
        self._row(cleanup_frame, 1, "Primary LLM model", self._primary_model_var, width=40)
        self._row(cleanup_frame, 2, "Fallback LLM model", self._fallback_model_var, width=40)
        self._row(cleanup_frame, 3, "Output language (optional)", self._output_language_var, width=20)
        ttk.Checkbutton(
            cleanup_frame,
            text="Send foreground window title as context to the cleanup model",
            variable=self._use_context_var,
        ).grid(row=4, column=0, sticky="w", padx=8, pady=6, columnspan=2)

        ui_frame = ttk.LabelFrame(general, text="UI")
        ui_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Checkbutton(
            ui_frame,
            text="Show floating recording overlay",
            variable=self._show_overlay_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        startup_frame = ttk.LabelFrame(general, text="Startup")
        startup_frame.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Checkbutton(
            startup_frame,
            text="Start Vocali automatically when I sign in to Windows",
            variable=self._auto_start_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        updates_frame = ttk.LabelFrame(general, text="Updates")
        updates_frame.grid(row=7, column=0, columnspan=3, sticky="ew", padx=12, pady=10)
        ttk.Checkbutton(
            updates_frame,
            text="Check GitHub for new versions on startup",
            variable=self._check_updates_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        general.columnconfigure(1, weight=1)

        # --- Shortcuts tab ---
        sc = ttk.Frame(nb)
        nb.add(sc, text="Shortcuts")
        ttk.Label(
            sc,
            text=(
                "Use the `keyboard` library syntax: comma-less, '+' joins keys.\n"
                "Examples: right alt   ctrl+right alt   ctrl+shift+space"
            ),
            foreground="#555",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self._row(sc, 1, "Hold-to-talk shortcut", self._hold_var, width=30)
        self._row(sc, 2, "Toggle dictation shortcut", self._toggle_var, width=30)

        edit_frame = ttk.LabelFrame(sc, text="Edit Mode")
        edit_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
        ttk.Checkbutton(
            edit_frame,
            text="Enable Edit Mode (transform highlighted text by voice)",
            variable=self._edit_enabled_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6, columnspan=2)
        ttk.Label(
            edit_frame,
            text=(
                "Hold the Edit shortcut, speak the transformation\n"
                '("make this shorter", "translate to French"), and release.'
            ),
            foreground="#555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))
        self._row(edit_frame, 2, "Edit Mode shortcut", self._edit_var, width=30)
        edit_frame.columnconfigure(1, weight=1)
        sc.columnconfigure(1, weight=1)

        # --- Vocabulary tab ---
        vocab = ttk.Frame(nb)
        nb.add(vocab, text="Vocabulary & prompt")
        ttk.Label(
            vocab,
            text="Custom vocabulary (one term per line, or comma-separated):",
        ).pack(anchor="w", padx=12, pady=(12, 4))
        self._vocab_text = tk.Text(vocab, height=6, wrap="word")
        self._vocab_text.insert("1.0", self._settings.custom_vocabulary)
        self._vocab_text.pack(fill="x", padx=12, pady=4)

        ttk.Label(
            vocab,
            text="Custom system prompt (leave empty to use the default):",
        ).pack(anchor="w", padx=12, pady=(12, 4))
        self._prompt_text = tk.Text(vocab, height=14, wrap="word")
        self._prompt_text.insert("1.0", self._settings.custom_system_prompt)
        self._prompt_text.pack(fill="both", expand=True, padx=12, pady=4)

        # --- Bottom buttons ---
        btns = ttk.Frame(self._root)
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text="Cancel", command=self._root.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Save", command=self._save).pack(side="right", padx=4)

    def _row(self, parent, row, label, var, width=30, show=None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=6)
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=6)

    def _read_api_key(self) -> str:
        """Read the API key, preferring the Entry widget over the StringVar.

        Tk's StringVar can desync from the bound Entry when the Tk root
        runs on a non-main thread (which is our case — pystray owns the
        main thread). Reading the widget directly is the reliable path.
        """
        widget_value = ""
        try:
            widget_value = self._api_key_entry.get() or ""
        except (tk.TclError, AttributeError):
            pass
        var_value = ""
        try:
            var_value = self._api_key_var.get() or ""
        except tk.TclError:
            pass
        return (widget_value or var_value).strip()

    def _toggle_api_key_visibility(self) -> None:
        try:
            self._api_key_entry.configure(
                show="" if self._show_key_var.get() else "*"
            )
        except tk.TclError:
            pass

    def _paste_api_key(self) -> None:
        try:
            text = self._root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Vocali", "Clipboard is empty.")
            return
        text = (text or "").strip()
        if not text:
            messagebox.showwarning("Vocali", "Clipboard is empty.")
            return
        # Write to BOTH the StringVar and the widget so whichever the rest
        # of the code reads from gets the new value.
        self._api_key_var.set(text)
        try:
            self._api_key_entry.delete(0, "end")
            self._api_key_entry.insert(0, text)
        except tk.TclError:
            pass

    def _test_api_key(self) -> None:
        key = self._read_api_key()
        url = self._base_url_var.get().strip() or "https://api.groq.com/openai/v1"
        if not key:
            messagebox.showwarning(
                "Vocali",
                "Enter an API key first. Use the Paste button or type it in.",
            )
            return
        # Persist immediately — losing the key because of a network blip
        # mid-test is brutal UX. Save first, validate second.
        try:
            config.set_api_key(key)
        except Exception as e:
            messagebox.showerror("Vocali", f"Could not save the API key: {e}")
            return
        ok = transcription.validate_api_key(key, base_url=url)
        if ok:
            messagebox.showinfo("Vocali", "API key is valid and saved.")
        else:
            messagebox.showerror(
                "Vocali",
                "API key was saved, but the validation request failed. "
                "Check the key and your internet, then try Test again.",
            )

    def _save(self) -> None:
        s = self._settings
        s.base_url = self._base_url_var.get().strip() or "https://api.groq.com/openai/v1"
        s.transcription_model = self._transcription_model_var.get().strip() or "whisper-large-v3"
        s.primary_llm_model = self._primary_model_var.get().strip()
        s.fallback_llm_model = self._fallback_model_var.get().strip()
        s.language = self._language_var.get().strip()
        s.output_language = self._output_language_var.get().strip()
        s.cleanup_enabled = bool(self._cleanup_var.get())
        s.hold_shortcut = self._hold_var.get().strip() or "right alt"
        s.toggle_shortcut = self._toggle_var.get().strip()
        s.edit_shortcut = self._edit_var.get().strip()
        s.edit_mode_enabled = bool(self._edit_enabled_var.get())
        s.show_overlay = bool(self._show_overlay_var.get())
        s.use_window_context = bool(self._use_context_var.get())
        s.auto_start = bool(self._auto_start_var.get())
        s.check_updates = bool(self._check_updates_var.get())
        s.custom_vocabulary = self._vocab_text.get("1.0", "end").strip()
        s.custom_system_prompt = self._prompt_text.get("1.0", "end").strip()
        try:
            s.save()
            config.set_api_key(self._read_api_key())
        except OSError as e:
            messagebox.showerror("Vocali", f"Failed to save settings: {e}")
            return
        try:
            auto_start.set_enabled(s.auto_start)
        except OSError as e:
            messagebox.showwarning(
                "Vocali",
                f"Settings saved but the auto-start registry update failed: {e}",
            )
        self._on_save(s)
        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()
