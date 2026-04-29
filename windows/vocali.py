"""Vocali for Windows — entry point.

Wires together: hotkeys → audio capture → Groq transcription → optional LLM
cleanup → paste-into-foreground-app. Runs as a tray icon.

Three pipelines share the same recorder:
- hold-to-talk dictation (default: Right Alt)
- toggle dictation (default: Ctrl + Right Alt)
- Edit Mode (default: Ctrl + Shift + Space): captures the current selection
  via Ctrl+C, records a voice command, asks the LLM to transform the
  selection, then pastes the result.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from enum import Enum

from PIL import Image, ImageDraw
import pystray

import config
import context_provider
import postprocessing
import transcription
from audio_recorder import AudioRecorder
from hotkeys import HotkeyManager
from paste import copy_selection, paste_text, restore_clipboard
from recording_overlay import RecordingOverlay
from settings_ui import SettingsWindow


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("vocali")


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    EDIT_RECORDING = "edit_recording"


# Mapping from app state to the visual state shown in the overlay/tray.
_OVERLAY_STATE = {
    State.IDLE: "idle",
    State.RECORDING: "recording",
    State.TRANSCRIBING: "transcribing",
    State.EDIT_RECORDING: "edit_recording",
}


class VocaliApp:
    def __init__(self) -> None:
        self._settings = config.Settings.load()
        self._recorder = AudioRecorder()
        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._toggle_active = False
        self._tray: pystray.Icon | None = None

        # Edit Mode session state (set during EDIT_RECORDING / TRANSCRIBING).
        self._edit_selection: str = ""
        self._edit_original_clipboard: str = ""
        self._edit_context: str = ""

        # Captured at the moment recording starts so the cleanup prompt
        # references the *original* focused app, not Vocali's own windows.
        self._captured_context: str = ""

        self._overlay: RecordingOverlay | None = None
        if self._settings.show_overlay:
            self._overlay = RecordingOverlay()

        self._hotkeys = HotkeyManager(
            hold_combo=self._settings.hold_shortcut,
            toggle_combo=self._settings.toggle_shortcut or None,
            edit_combo=self._edit_combo(),
            on_hold_start=self._on_hold_start,
            on_hold_end=self._on_hold_end,
            on_toggle=self._on_toggle,
            on_edit_start=self._on_edit_start,
            on_edit_end=self._on_edit_end,
        )

    def _edit_combo(self) -> str | None:
        if not self._settings.edit_mode_enabled:
            return None
        return self._settings.edit_shortcut or None

    # ---- lifecycle ----

    def run(self) -> None:
        if self._overlay is not None:
            self._overlay.start()
        self._hotkeys.start()
        try:
            self._tray = pystray.Icon(
                "vocali",
                self._make_icon(State.IDLE),
                "Vocali",
                menu=self._make_menu(),
            )
            log.info(
                "Vocali started. Hold [%s] dictation, toggle [%s], edit [%s].",
                self._settings.hold_shortcut,
                self._settings.toggle_shortcut or "none",
                self._edit_combo() or "off",
            )
            if not config.get_api_key():
                log.warning("No API key set yet — open Settings from the tray to add one.")
            self._tray.run()
        finally:
            self._hotkeys.stop()
            self._recorder.cancel()
            if self._overlay is not None:
                self._overlay.stop()

    def _quit(self, icon=None, item=None) -> None:  # noqa: ARG002
        if self._tray is not None:
            self._tray.stop()

    # ---- tray ----

    def _make_icon(self, state: State) -> Image.Image:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if state in (State.RECORDING, State.EDIT_RECORDING):
            color = (122, 169, 255, 255) if state is State.EDIT_RECORDING else (220, 50, 50, 255)
            d.ellipse((10, 10, size - 10, size - 10), fill=color)
        elif state is State.TRANSCRIBING:
            color = (240, 180, 40, 255)
            d.ellipse((10, 10, size - 10, size - 10), outline=color, width=6)
        else:
            color = (200, 200, 200, 255)
            bars = [(8, 28, 4, 8), (18, 22, 4, 20), (28, 16, 4, 32),
                    (38, 22, 4, 20), (48, 28, 4, 8)]
            for x, y, w, h in bars:
                d.rectangle((x, y, x + w, y + h), fill=color)
        return img

    def _make_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Settings…", self._open_settings),
            pystray.MenuItem("Status: idle", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _open_settings(self, icon=None, item=None) -> None:  # noqa: ARG002
        # tkinter wants its own thread because pystray owns the main thread.
        threading.Thread(target=self._run_settings_window, daemon=True).start()

    def _run_settings_window(self) -> None:
        try:
            window = SettingsWindow(self._settings, on_save=self._apply_settings)
            window.run()
        except Exception:
            log.error("Settings window crashed:\n%s", traceback.format_exc())

    def _apply_settings(self, settings: config.Settings) -> None:
        self._settings = settings
        self._hotkeys.update(
            hold_combo=settings.hold_shortcut,
            toggle_combo=settings.toggle_shortcut or None,
            edit_combo=self._edit_combo(),
        )
        # Toggle overlay on/off without crashing if Tk wasn't running.
        if settings.show_overlay and self._overlay is None:
            self._overlay = RecordingOverlay()
            self._overlay.start()
        elif not settings.show_overlay and self._overlay is not None:
            self._overlay.stop()
            self._overlay = None
        log.info("Settings updated.")

    # ---- state transitions ----

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            self._state = state
        if self._tray is not None:
            self._tray.icon = self._make_icon(state)
        if self._overlay is not None:
            self._overlay.set_state(_OVERLAY_STATE[state])

    # ---- hotkey handlers (called from the keyboard hook thread) ----

    def _on_hold_start(self) -> None:
        if self._state is not State.IDLE:
            return
        self._begin_recording(via_toggle=False)

    def _on_hold_end(self) -> None:
        if self._toggle_active:
            return
        if self._state is State.RECORDING:
            self._finish_recording()

    def _on_toggle(self) -> None:
        if self._state is State.RECORDING and self._toggle_active:
            self._finish_recording()
            return
        if self._state is State.IDLE:
            self._begin_recording(via_toggle=True)

    def _on_edit_start(self) -> None:
        if self._state is not State.IDLE:
            return
        self._begin_edit_recording()

    def _on_edit_end(self) -> None:
        if self._state is State.EDIT_RECORDING:
            self._finish_edit_recording()

    # ---- regular dictation pipeline ----

    def _capture_context(self) -> str:
        if not self._settings.use_window_context:
            return ""
        try:
            return context_provider.context_summary()
        except Exception:
            return ""

    def _begin_recording(self, via_toggle: bool) -> None:
        # Capture context BEFORE we enter recording mode — once our overlay
        # is shown, GetForegroundWindow may return our window instead.
        self._captured_context = self._capture_context()
        try:
            self._recorder.start()
        except Exception as e:
            log.error("Failed to start recording: %s", e)
            return
        self._toggle_active = via_toggle
        self._set_state(State.RECORDING)
        log.info("Recording (%s)", "toggle" if via_toggle else "hold")

    def _finish_recording(self) -> None:
        self._toggle_active = False
        try:
            wav_bytes = self._recorder.stop()
        except Exception as e:
            log.error("Failed to stop recording: %s", e)
            self._set_state(State.IDLE)
            return

        if not wav_bytes:
            log.info("No audio captured.")
            self._set_state(State.IDLE)
            return

        self._set_state(State.TRANSCRIBING)
        threading.Thread(
            target=self._process_audio,
            args=(wav_bytes, self._captured_context),
            daemon=True,
        ).start()

    def _process_audio(self, wav_bytes: bytes, ctx: str) -> None:
        try:
            api_key = config.get_api_key()
            if not api_key:
                log.error("No Groq API key set. Open Settings from the tray.")
                return

            log.info("Transcribing %d bytes…", len(wav_bytes))
            try:
                raw = transcription.transcribe(
                    wav_bytes,
                    api_key=api_key,
                    base_url=self._settings.base_url,
                    model=self._settings.transcription_model,
                    language=self._settings.language or None,
                )
            except transcription.TranscriptionError as e:
                log.error("Transcription failed: %s", e)
                return

            if not raw.strip():
                log.info("Transcript empty (silence or hallucination filter).")
                return

            final = raw
            if self._settings.cleanup_enabled:
                try:
                    cleaned = postprocessing.post_process(
                        raw,
                        api_key=api_key,
                        base_url=self._settings.base_url,
                        primary_model=self._settings.primary_llm_model,
                        fallback_model=self._settings.fallback_llm_model,
                        custom_vocabulary=self._settings.custom_vocabulary,
                        custom_system_prompt=self._settings.custom_system_prompt,
                        output_language=self._settings.output_language,
                        context_summary=ctx,
                    )
                    if cleaned.strip():
                        final = cleaned
                    else:
                        log.info("Cleanup returned empty; pasting raw transcript.")
                except postprocessing.PostProcessingError as e:
                    log.warning("Post-processing failed (%s); pasting raw transcript.", e)

            log.info("Pasting %d chars.", len(final))
            paste_text(final)
        except Exception:
            log.error("Pipeline crashed:\n%s", traceback.format_exc())
        finally:
            self._set_state(State.IDLE)

    # ---- Edit Mode pipeline ----

    def _begin_edit_recording(self) -> None:
        # Grab context + selection before recording starts.
        self._edit_context = self._capture_context()
        try:
            selection, original = copy_selection()
        except Exception as e:
            log.error("Failed to read selection for Edit Mode: %s", e)
            return

        if not selection.strip():
            log.info("Edit Mode: no selection detected, ignoring.")
            # Restore whatever the user had on their clipboard before our probe.
            restore_clipboard(original)
            return

        self._edit_selection = selection
        self._edit_original_clipboard = original

        try:
            self._recorder.start()
        except Exception as e:
            log.error("Failed to start recording for Edit Mode: %s", e)
            restore_clipboard(original)
            return

        self._set_state(State.EDIT_RECORDING)
        log.info("Edit Mode recording on %d-char selection.", len(selection))

    def _finish_edit_recording(self) -> None:
        try:
            wav_bytes = self._recorder.stop()
        except Exception as e:
            log.error("Failed to stop Edit Mode recording: %s", e)
            self._set_state(State.IDLE)
            self._reset_edit_state()
            return

        selection = self._edit_selection
        original_clipboard = self._edit_original_clipboard
        ctx = self._edit_context

        if not wav_bytes:
            log.info("Edit Mode: no audio captured.")
            restore_clipboard(original_clipboard)
            self._set_state(State.IDLE)
            self._reset_edit_state()
            return

        self._set_state(State.TRANSCRIBING)
        threading.Thread(
            target=self._process_edit_audio,
            args=(wav_bytes, selection, original_clipboard, ctx),
            daemon=True,
        ).start()

    def _process_edit_audio(
        self,
        wav_bytes: bytes,
        selection: str,
        original_clipboard: str,
        ctx: str,
    ) -> None:
        try:
            api_key = config.get_api_key()
            if not api_key:
                log.error("No Groq API key set. Open Settings from the tray.")
                return

            try:
                command = transcription.transcribe(
                    wav_bytes,
                    api_key=api_key,
                    base_url=self._settings.base_url,
                    model=self._settings.transcription_model,
                    language=self._settings.language or None,
                )
            except transcription.TranscriptionError as e:
                log.error("Edit Mode transcription failed: %s", e)
                return

            if not command.strip():
                log.info("Edit Mode: empty voice command, leaving selection alone.")
                return

            try:
                replacement = postprocessing.command_transform(
                    selected_text=selection,
                    voice_command=command,
                    api_key=api_key,
                    base_url=self._settings.base_url,
                    primary_model=self._settings.primary_llm_model,
                    fallback_model=self._settings.fallback_llm_model,
                    custom_vocabulary=self._settings.custom_vocabulary,
                    output_language=self._settings.output_language,
                    context_summary=ctx,
                )
            except postprocessing.PostProcessingError as e:
                log.error("Edit Mode transform failed: %s", e)
                return

            if not replacement.strip():
                log.info("Edit Mode transform returned empty; not replacing.")
                return

            log.info("Edit Mode: pasting %d-char replacement.", len(replacement))
            paste_text(replacement)
            # Wait for the paste to settle, then restore the user's
            # pre-Edit-Mode clipboard. paste_text() clobbered it.
            time.sleep(0.15)
            restore_clipboard(original_clipboard)
        except Exception:
            log.error("Edit pipeline crashed:\n%s", traceback.format_exc())
            restore_clipboard(original_clipboard)
        finally:
            self._set_state(State.IDLE)
            self._reset_edit_state()

    def _reset_edit_state(self) -> None:
        self._edit_selection = ""
        self._edit_original_clipboard = ""
        self._edit_context = ""


def main() -> int:
    try:
        VocaliApp().run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
