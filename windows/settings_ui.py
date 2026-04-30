"""Settings window. Themed with sv-ttk so it matches Windows 11.

Runs on its own thread when opened from the tray (pystray owns the main
thread). All read paths for the API key go through ``_read_api_key()``
which reads the Entry widget directly — Tk's StringVar can desync from
its bound Entry when the Tk root runs on a non-main thread.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

import auto_start
import config
import theme
import transcription


# Larger top-level paddings give the window the editorial feel of the
# Mac FreeFlow Settings pane instead of the usual cramped Tk form.
PAD_X = 24
PAD_Y = 14
SECTION_PAD_Y = 18


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
        self._root.geometry("720x720")
        self._root.minsize(680, 660)

        # Apply the Windows 11 theme — auto-detects user's system mode.
        self._theme_mode = theme.apply(self._root)

        self._init_vars()
        self._build()

    # --------------------------------------------------------------- vars

    def _init_vars(self) -> None:
        s = self._settings
        self._api_key_var = tk.StringVar(value=config.get_api_key())
        self._show_key_var = tk.BooleanVar(value=False)
        self._base_url_var = tk.StringVar(value=s.base_url)
        self._transcription_model_var = tk.StringVar(value=s.transcription_model)
        self._primary_model_var = tk.StringVar(value=s.primary_llm_model)
        self._fallback_model_var = tk.StringVar(value=s.fallback_llm_model)
        self._language_var = tk.StringVar(value=s.language)
        self._output_language_var = tk.StringVar(value=s.output_language)
        self._cleanup_var = tk.BooleanVar(value=s.cleanup_enabled)
        self._hold_var = tk.StringVar(value=s.hold_shortcut)
        self._toggle_var = tk.StringVar(value=s.toggle_shortcut)
        self._edit_var = tk.StringVar(value=s.edit_shortcut)
        self._edit_enabled_var = tk.BooleanVar(value=s.edit_mode_enabled)
        self._show_overlay_var = tk.BooleanVar(value=s.show_overlay)
        self._use_context_var = tk.BooleanVar(value=s.use_window_context)
        # Source of truth for "auto-start" is the registry, so we always
        # query it fresh. A user can toggle the Run key elsewhere
        # (msconfig, Task Manager) and we want the UI to reflect that.
        self._auto_start_var = tk.BooleanVar(value=auto_start.is_enabled())
        self._check_updates_var = tk.BooleanVar(value=s.check_updates)

    # -------------------------------------------------------------- build

    def _build(self) -> None:
        # Header strip with title + tagline. Keeps the tabs-in-a-bare-window
        # look from feeling clinical.
        header = ttk.Frame(self._root)
        header.pack(fill="x", padx=PAD_X, pady=(PAD_Y + 6, 6))
        ttk.Label(header, text="Vocali", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Voice-to-text dictation for Windows.",
            foreground=theme.palette(self._theme_mode)["ink_dim"],
        ).pack(anchor="w", pady=(2, 0))

        nb = ttk.Notebook(self._root)
        nb.pack(fill="both", expand=True, padx=PAD_X, pady=(SECTION_PAD_Y, 0))

        nb.add(self._build_general_tab(nb), text="  General  ")
        nb.add(self._build_shortcuts_tab(nb), text="  Shortcuts  ")
        nb.add(self._build_vocabulary_tab(nb), text="  Vocabulary  ")

        # Footer: Cancel + Save, right-aligned.
        footer = ttk.Frame(self._root)
        footer.pack(fill="x", padx=PAD_X, pady=PAD_Y)
        ttk.Button(footer, text="Cancel", command=self._root.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Save", style="Accent.TButton", command=self._save).pack(side="right")

    # --------------------------------------------------------- General tab

    def _build_general_tab(self, parent) -> ttk.Frame:
        outer, frame = self._scrollable_frame(parent)

        self._section(frame, "Provider", "Where Vocali sends audio for transcription.")
        self._build_api_key_row(frame)
        self._labelled_row(frame, "Base URL", self._base_url_var,
                           hint="Default is Groq. Any OpenAI-compatible endpoint works.")
        self._labelled_row(frame, "Transcription model", self._transcription_model_var,
                           hint="Default: whisper-large-v3.")
        self._labelled_row(frame, "Spoken language", self._language_var,
                           hint="ISO code like 'fr' or 'en'. Leave empty for auto-detect.",
                           width=12)

        self._section(frame, "Post-processing",
                      "Optional LLM cleanup pass after transcription.")
        ttk.Checkbutton(
            frame,
            text="Enable LLM cleanup (remove fillers, fix punctuation, preserve names)",
            variable=self._cleanup_var,
        ).pack(anchor="w", padx=PAD_X, pady=(0, 8))
        self._labelled_row(frame, "Primary model", self._primary_model_var,
                           hint="Default: openai/gpt-oss-20b")
        self._labelled_row(frame, "Fallback model", self._fallback_model_var,
                           hint="Used when the primary returns 429 or empty.")
        self._labelled_row(frame, "Output language", self._output_language_var,
                           hint="Force a target language (e.g. 'English'). Empty = same as spoken.",
                           width=20)
        ttk.Checkbutton(
            frame,
            text="Send foreground window context (titles + accessibility text)",
            variable=self._use_context_var,
        ).pack(anchor="w", padx=PAD_X, pady=(8, 0))

        self._section(frame, "Interface", "How Vocali appears on your desktop.")
        ttk.Checkbutton(
            frame,
            text="Show floating recording overlay",
            variable=self._show_overlay_var,
        ).pack(anchor="w", padx=PAD_X)

        self._section(frame, "System")
        ttk.Checkbutton(
            frame,
            text="Start Vocali automatically when I sign in to Windows",
            variable=self._auto_start_var,
        ).pack(anchor="w", padx=PAD_X, pady=(0, 6))
        ttk.Checkbutton(
            frame,
            text="Check GitHub for new versions on startup",
            variable=self._check_updates_var,
        ).pack(anchor="w", padx=PAD_X)

        return outer

    def _build_api_key_row(self, parent) -> None:
        ttk.Label(parent, text="API key", font=("Segoe UI", 10)).pack(
            anchor="w", padx=PAD_X, pady=(0, 4)
        )
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=PAD_X, pady=(0, 4))
        self._api_key_entry = ttk.Entry(
            row, textvariable=self._api_key_var, show="*"
        )
        self._api_key_entry.pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(
            row, text="Show", variable=self._show_key_var,
            command=self._toggle_api_key_visibility,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Paste", command=self._paste_api_key).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Test", command=self._test_api_key).pack(side="left", padx=(4, 0))
        ttk.Label(
            parent,
            text="Get a free key at console.groq.com/keys.",
            foreground=theme.palette(self._theme_mode)["ink_dim"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=PAD_X, pady=(0, SECTION_PAD_Y))

    # ------------------------------------------------------- Shortcuts tab

    def _build_shortcuts_tab(self, parent) -> ttk.Frame:
        outer, frame = self._scrollable_frame(parent)

        self._section(frame, "Dictation",
                      "Hold to talk and release. Or tap a different combo to latch on.")
        self._labelled_row(frame, "Hold-to-talk", self._hold_var,
                           hint="Default: right alt. While held, Vocali records.")
        self._labelled_row(frame, "Toggle dictation", self._toggle_var,
                           hint="Default: ctrl+right alt. Tap once to start, again to stop.")

        self._section(frame, "Edit Mode",
                      "Highlight text, hold the shortcut, speak a transformation.")
        ttk.Checkbutton(
            frame,
            text="Enable Edit Mode",
            variable=self._edit_enabled_var,
        ).pack(anchor="w", padx=PAD_X, pady=(0, 8))
        self._labelled_row(frame, "Edit shortcut", self._edit_var,
                           hint='Default: ctrl+shift+space. Try "make this shorter" or '
                                '"translate to French".')

        ttk.Label(
            frame,
            text=(
                "Combo syntax (from the keyboard library): keys joined with '+'.\n"
                "Examples: right alt   ctrl+right alt   ctrl+shift+space"
            ),
            foreground=theme.palette(self._theme_mode)["ink_dim"],
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w", padx=PAD_X, pady=(SECTION_PAD_Y, 0))

        return outer

    # ------------------------------------------------------ Vocabulary tab

    def _build_vocabulary_tab(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)

        self._section(frame, "Custom vocabulary",
                      "Names, jargon, project-specific words. The cleanup model "
                      "preserves these spellings.")
        self._vocab_text = tk.Text(frame, height=6, wrap="word",
                                   font=("Segoe UI", 10), relief="flat",
                                   padx=10, pady=8)
        self._vocab_text.insert("1.0", self._settings.custom_vocabulary)
        self._vocab_text.pack(fill="x", padx=PAD_X, pady=(0, SECTION_PAD_Y))

        self._section(frame, "System prompt",
                      "Override the default cleanup instructions. Leave empty to "
                      "use Vocali's tested prompt.")
        self._prompt_text = tk.Text(frame, height=18, wrap="word",
                                    font=("Segoe UI", 10), relief="flat",
                                    padx=10, pady=8)
        self._prompt_text.insert("1.0", self._settings.custom_system_prompt)
        self._prompt_text.pack(fill="both", expand=True, padx=PAD_X, pady=(0, PAD_Y))

        self._style_text_widget(self._vocab_text)
        self._style_text_widget(self._prompt_text)

        return frame

    # -------------------------------------------------------------- helpers

    def _scrollable_frame(self, parent) -> tuple[ttk.Frame, ttk.Frame]:
        """Vertical scroll container — Settings have grown enough that
        forcing fixed height makes things feel cramped.

        Returns ``(outer, inner)``: ``outer`` is the Notebook-attachable
        container, ``inner`` is the frame to pack widgets into.
        """
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0,
                           bg=self._root.cget("bg") if "bg" in self._root.keys() else "")
        try:
            canvas.configure(bg=self._theme_canvas_bg())
        except Exception:
            pass
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _resize)

        # Mouse-wheel: native scroll inside the form.
        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)

        return outer, inner

    def _theme_canvas_bg(self) -> str:
        try:
            style = ttk.Style()
            return style.lookup("TFrame", "background") or ""
        except Exception:
            return ""

    def _section(self, parent, title: str, subtitle: str | None = None) -> None:
        wrap = ttk.Frame(parent)
        wrap.pack(fill="x", padx=PAD_X, pady=(SECTION_PAD_Y, 6))
        ttk.Label(wrap, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        if subtitle:
            ttk.Label(
                wrap, text=subtitle, font=("Segoe UI", 9),
                foreground=theme.palette(self._theme_mode)["ink_dim"],
                wraplength=620, justify="left",
            ).pack(anchor="w", pady=(2, 6))

    def _labelled_row(
        self,
        parent,
        label: str,
        var: tk.StringVar,
        hint: str | None = None,
        width: int = 0,
    ) -> None:
        ttk.Label(parent, text=label, font=("Segoe UI", 10)).pack(
            anchor="w", padx=PAD_X, pady=(0, 4)
        )
        if width:
            entry = ttk.Entry(parent, textvariable=var, width=width)
            entry.pack(anchor="w", padx=PAD_X, pady=(0, 2 if hint else 12))
        else:
            entry = ttk.Entry(parent, textvariable=var)
            entry.pack(fill="x", padx=PAD_X, pady=(0, 2 if hint else 12))
        if hint:
            ttk.Label(
                parent, text=hint,
                foreground=theme.palette(self._theme_mode)["ink_dim"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", padx=PAD_X, pady=(0, 12))

    def _style_text_widget(self, widget: tk.Text) -> None:
        try:
            p = theme.palette(self._theme_mode)
            widget.configure(bg=p["surface"], fg=p["ink"], insertbackground=p["ink"])
        except Exception:
            pass

    # -------------------------------------------------- API key + actions

    def _read_api_key(self) -> str:
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

    # ------------------------------------------------------------ save

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
