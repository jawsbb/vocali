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

        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        nb = ttk.Notebook(self._root)
        nb.pack(fill="both", expand=True, **pad)

        # --- General tab ---
        general = ttk.Frame(nb)
        nb.add(general, text="General")
        self._row(general, 0, "Groq API key", self._api_key_var, show="*", width=48)
        ttk.Button(
            general, text="Test API key", command=self._test_api_key
        ).grid(row=0, column=2, padx=8, pady=6)

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

    def _test_api_key(self) -> None:
        key = self._api_key_var.get().strip()
        url = self._base_url_var.get().strip() or "https://api.groq.com/openai/v1"
        if not key:
            messagebox.showwarning("Vocali", "Enter an API key first.")
            return
        ok = transcription.validate_api_key(key, base_url=url)
        if ok:
            messagebox.showinfo("Vocali", "API key is valid.")
        else:
            messagebox.showerror("Vocali", "API key check failed.")

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
        s.custom_vocabulary = self._vocab_text.get("1.0", "end").strip()
        s.custom_system_prompt = self._prompt_text.get("1.0", "end").strip()
        try:
            s.save()
            config.set_api_key(self._api_key_var.get().strip())
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
