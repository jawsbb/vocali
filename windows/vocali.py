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

import concurrent.futures
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
import webbrowser
from enum import Enum
from pathlib import Path


# Context capture can take ~100–800 ms (UI Automation walks the focused app's
# accessibility tree). Run it on a dedicated worker so recording starts
# immediately and we wait on the future only when we're about to call the LLM.
CONTEXT_WAIT_TIMEOUT_S = 1.5


def _log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    p = Path(base) / "Vocali"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _setup_logging() -> None:
    """Console + rotating file. The file lets us diagnose --windowed builds
    where stderr is silently discarded by the PyInstaller windowed launcher."""
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console (a no-op in --windowed PyInstaller builds, but useful from source).
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    try:
        log_path = _log_dir() / "vocali.log"
        rotating = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        rotating.setFormatter(fmt)
        root.addHandler(rotating)
    except Exception:
        # Never let logging setup itself crash the app.
        pass

    # `comtypes` and `uiautomation` log at INFO on every COM cache access.
    logging.getLogger("comtypes").setLevel(logging.WARNING)
    logging.getLogger("comtypes.client").setLevel(logging.WARNING)
    logging.getLogger("comtypes.client._code_cache").setLevel(logging.WARNING)


_setup_logging()
log = logging.getLogger("vocali")


# Heavy imports come after logging is configured so any ImportError gets
# captured in the log file (vital for diagnosing PyInstaller-bundled builds).
from PIL import Image, ImageDraw  # noqa: E402
import pystray  # noqa: E402

import config  # noqa: E402
import context_provider  # noqa: E402
import postprocessing  # noqa: E402
import transcription  # noqa: E402
import updater  # noqa: E402
from audio_recorder import AudioRecorder  # noqa: E402
from hotkeys import HotkeyManager  # noqa: E402
from paste import copy_selection, paste_text, restore_clipboard  # noqa: E402
from recording_overlay import RecordingOverlay  # noqa: E402
from settings_ui import SettingsWindow  # noqa: E402
from version import VERSION  # noqa: E402


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

        # Captured at the moment recording starts so the cleanup prompt
        # references the *original* focused app, not Vocali's own windows.
        # Future-based so the UIA walk runs in parallel with the recorder
        # starting up — otherwise the user's first word is lost.
        self._context_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vocali-context"
        )
        self._captured_context_future: concurrent.futures.Future[str] | None = None

        self._overlay: RecordingOverlay | None = None
        if self._settings.show_overlay:
            self._overlay = RecordingOverlay()

        self._update_info: updater.UpdateInfo | None = None
        self._update_check_lock = threading.Lock()

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
                self._tray_title(),
                menu=self._make_menu(),
            )
            log.info(
                "Vocali v%s started. Hold [%s] dictation, toggle [%s], edit [%s].",
                VERSION,
                self._settings.hold_shortcut,
                self._settings.toggle_shortcut or "none",
                self._edit_combo() or "off",
            )
            if not config.get_api_key():
                log.warning("No API key set yet — opening Settings for onboarding.")
                # Tray apps with no UI on launch are confusing for first-time
                # users. If there's no API key, open Settings automatically
                # so the user lands somewhere they can act on. A short delay
                # lets the tray icon paint first so the toast actually shows.
                threading.Timer(1.2, self._show_onboarding).start()
            if self._settings.check_updates:
                # Defer the network call so app startup feels instant.
                threading.Timer(20.0, self._check_for_updates_async,
                                kwargs={"silent": True}).start()
            self._tray.run()
        finally:
            self._hotkeys.stop()
            self._recorder.cancel()
            if self._overlay is not None:
                self._overlay.stop()
            self._context_executor.shutdown(wait=False, cancel_futures=True)

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

    def _tray_title(self) -> str:
        if self._update_info is not None:
            return f"Vocali v{VERSION} — update v{self._update_info.version} available"
        return f"Vocali v{VERSION}"

    def _make_menu(self) -> pystray.Menu:
        items: list = [pystray.MenuItem("Settings…", self._open_settings)]
        if self._update_info is not None:
            items.append(pystray.MenuItem(
                f"Update to v{self._update_info.version}",
                self._open_update_page,
            ))
        items.append(pystray.MenuItem(f"Vocali v{VERSION}", lambda: None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem(
            "Check for updates…",
            self._on_check_for_updates_clicked,
        ))
        items.append(pystray.MenuItem("Quit", self._quit))
        return pystray.Menu(*items)

    def _refresh_tray(self) -> None:
        if self._tray is None:
            return
        self._tray.title = self._tray_title()
        self._tray.menu = self._make_menu()
        try:
            self._tray.update_menu()
        except Exception:
            pass

    def _open_update_page(self, icon=None, item=None) -> None:  # noqa: ARG002
        info = self._update_info
        if info is None or not info.html_url:
            return
        try:
            webbrowser.open(info.html_url)
        except Exception:
            log.error("Failed to open release page: %s", info.html_url)

    def _on_check_for_updates_clicked(self, icon=None, item=None) -> None:  # noqa: ARG002
        threading.Thread(
            target=self._check_for_updates_async,
            kwargs={"silent": False},
            daemon=True,
        ).start()

    def _check_for_updates_async(self, silent: bool = True) -> None:
        # Coalesce concurrent checks so menu spam doesn't fire N requests.
        if not self._update_check_lock.acquire(blocking=False):
            return
        try:
            log.info("Checking for updates… (current v%s)", VERSION)
            info = updater.check_for_update(VERSION)
            self._update_info = info
            if info is not None:
                log.info("Update available: v%s — %s", info.version, info.html_url)
                self._notify_update(info)
            else:
                log.info("No update available.")
                if not silent and self._tray is not None:
                    try:
                        self._tray.notify("Vocali", f"You're on the latest version (v{VERSION}).")
                    except Exception:
                        pass
            self._refresh_tray()
        finally:
            self._update_check_lock.release()

    def _notify_update(self, info: updater.UpdateInfo) -> None:
        if self._tray is None:
            return
        try:
            self._tray.notify(
                f"Vocali v{info.version} available",
                f"Click the tray icon → Update to v{info.version}.",
            )
        except Exception:
            # pystray's notify can fail on some Windows configurations; the
            # menu item is still visible so the user can find it manually.
            pass

    def _open_settings(self, icon=None, item=None) -> None:  # noqa: ARG002
        # tkinter wants its own thread because pystray owns the main thread.
        threading.Thread(target=self._run_settings_window, daemon=True).start()

    def _run_settings_window(self) -> None:
        try:
            window = SettingsWindow(self._settings, on_save=self._apply_settings)
            window.run()
        except Exception:
            log.error("Settings window crashed:\n%s", traceback.format_exc())

    def _show_onboarding(self) -> None:
        """Welcome flow for the first-run-with-no-API-key case.

        We post a Windows toast pointing at the tray icon (so the user
        learns where Vocali lives) and then open the Settings window so
        they have a place to paste their key.
        """
        if self._tray is not None:
            try:
                self._tray.notify(
                    "Vocali is running",
                    "Look for the waveform icon in the system tray "
                    "(near the clock — you may need to expand hidden icons). "
                    "Settings is opening so you can paste your Groq API key.",
                )
            except Exception:
                pass
        self._open_settings()

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

    def _start_context_capture(self) -> None:
        """Submit context capture to the worker BEFORE recording starts.

        Reading the foreground window must happen before the overlay shows
        (otherwise GetForegroundWindow returns our overlay). The Win32
        layer is fast (~5 ms) but UI Automation can take 100–800 ms — by
        running the whole capture on the worker thread, the recorder gets
        to start immediately and we wait on the future at LLM-call time.
        """
        if not self._settings.use_window_context:
            self._captured_context_future = None
            return

        def capture() -> str:
            try:
                return context_provider.context_summary()
            except Exception:
                return ""

        self._captured_context_future = self._context_executor.submit(capture)

    def _resolve_captured_context(self) -> str:
        future = self._captured_context_future
        self._captured_context_future = None
        if future is None:
            return ""
        try:
            return future.result(timeout=CONTEXT_WAIT_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            log.info("Context capture timed out; cleanup runs without it.")
            future.cancel()
            return ""
        except Exception:
            return ""

    def _begin_recording(self, via_toggle: bool) -> None:
        # Capture context BEFORE entering recording mode — once our overlay
        # is shown, GetForegroundWindow may return our window instead.
        self._start_context_capture()
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
            self._captured_context_future = None
            self._set_state(State.IDLE)
            return

        ctx = self._resolve_captured_context()
        self._set_state(State.TRANSCRIBING)
        threading.Thread(
            target=self._process_audio,
            args=(wav_bytes, ctx),
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
        # Kick off context capture in parallel — see _start_context_capture.
        self._start_context_capture()
        try:
            selection, original = copy_selection()
        except Exception as e:
            log.error("Failed to read selection for Edit Mode: %s", e)
            self._captured_context_future = None
            return

        if not selection.strip():
            log.info("Edit Mode: no selection detected, ignoring.")
            # Restore whatever the user had on their clipboard before our probe.
            restore_clipboard(original)
            self._captured_context_future = None
            return

        self._edit_selection = selection
        self._edit_original_clipboard = original

        try:
            self._recorder.start()
        except Exception as e:
            log.error("Failed to start recording for Edit Mode: %s", e)
            restore_clipboard(original)
            self._captured_context_future = None
            return

        self._set_state(State.EDIT_RECORDING)
        log.info("Edit Mode recording on %d-char selection.", len(selection))

    def _finish_edit_recording(self) -> None:
        try:
            wav_bytes = self._recorder.stop()
        except Exception as e:
            log.error("Failed to stop Edit Mode recording: %s", e)
            self._captured_context_future = None
            self._set_state(State.IDLE)
            self._reset_edit_state()
            return

        selection = self._edit_selection
        original_clipboard = self._edit_original_clipboard

        if not wav_bytes:
            log.info("Edit Mode: no audio captured.")
            restore_clipboard(original_clipboard)
            self._captured_context_future = None
            self._set_state(State.IDLE)
            self._reset_edit_state()
            return

        ctx = self._resolve_captured_context()
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


def _write_startup_error(exc: BaseException) -> None:
    """Last-resort dumper for boot crashes.

    `_setup_logging()` should already be writing to vocali.log, but if
    that itself failed we still want a paper trail somewhere. Try the
    LOCALAPPDATA dir first, then the user profile, then the cwd.
    """
    payload = (
        f"Vocali v{VERSION} startup crashed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"sys.executable={sys.executable}\n"
        f"sys.argv={sys.argv!r}\n"
        f"frozen={getattr(sys, 'frozen', False)}\n"
        f"_MEIPASS={getattr(sys, '_MEIPASS', None)!r}\n\n"
        + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )
    candidates = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        os.path.expanduser("~"),
        os.getcwd(),
    ]
    for base in candidates:
        if not base:
            continue
        try:
            target_dir = Path(base) / "Vocali"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "vocali.startup_error.log").write_text(payload, encoding="utf-8")
            return
        except Exception:
            continue


def main() -> int:
    try:
        log.info("Vocali v%s booting (frozen=%s, exe=%s)",
                 VERSION, getattr(sys, "frozen", False), sys.executable)
        VocaliApp().run()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log.error("Fatal startup error", exc_info=True)
        _write_startup_error(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
