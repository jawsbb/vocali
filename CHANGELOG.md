# Changelog

All notable changes to Vocali are documented here.

Vocali is a fork of [FreeFlow](https://github.com/zachlatta/freeflow). The history below up to `0.3.3` is inherited from upstream FreeFlow; entries from `0.4.0` onward are Vocali changes.

This project uses semantic versioning for public releases. Use `MAJOR.MINOR.PATCH`, where:

- `MAJOR` changes include breaking behavior or major compatibility changes.
- `MINOR` changes add user-visible features and improvements.
- `PATCH` changes fix bugs, polish existing behavior, or make small internal improvements.

## [0.4.5] - Unreleased

### Fixed

- Windows: dictation was being pasted twice (or more) when multiple Vocali processes were running simultaneously. Each instance installed its own global keyboard hook, so a single Right Alt press fired all of them. Vocali now grabs a per-user named Windows mutex on startup; secondary launches show a "Vocali is already running" message and exit before installing any hooks.

## [0.4.4] - Unreleased

### Changed

- Windows Settings: redesigned with the Windows 11 fluent look (sv-ttk theme) and an editorial-style layout reminiscent of the Mac FreeFlow Settings pane. Sections now have proper titles, descriptive subtitles, generous spacing, and a window header. Light / dark mode is auto-detected from the system `AppsUseLightTheme` registry value.
- Windows Settings: tabs (General / Shortcuts / Vocabulary) now scroll vertically instead of forcing a fixed 600 px-tall window.
- Windows recording overlay: pulls colors from the same theme palette so it matches the rest of the app (and the user's system mode).

### Added

- New `theme.py` module: system-mode detection + sv-ttk application + a shared color palette used by both the Settings window and the recording overlay.

## [0.4.3] - 2026-04-30

### Fixed

- Windows Settings: API key field could appear filled (asterisks visible) but `.get()` returned empty, so Test API key reported "Enter an API key first" and Save dropped the key. Caused by Tk StringVar desyncing from the Entry widget when the Tk root runs on a non-main thread. Settings now reads the Entry widget directly with the StringVar as fallback.

### Added

- Windows Settings: explicit **Paste** button next to the API key field that uses Tk's `clipboard_get()`. Bypasses any interaction between Ctrl+V and the global keyboard hook.
- Windows Settings: **Show** checkbox to unmask the API key while typing/verifying.
- Windows Settings: **Test** now saves the key first, then validates. A failed network test no longer loses your paste.

## [0.4.2] - 2026-04-30

### Added

- Windows: first-run onboarding. When Vocali boots without a Groq API key configured, it now posts a toast pointing the user at the tray icon and opens the Settings window automatically so they have somewhere to act. Tray-only apps can be invisible to first-time users; this gives them a clear handoff.

## [0.4.1] - 2026-04-29

### Added

- Windows: rotating log file at `%LOCALAPPDATA%\Vocali\vocali.log` (keeps the last ~1.5 MB of session logs). Lets you diagnose silent failures in the windowed `.exe` build.
- Windows: top-level startup-exception catcher that writes a full traceback to `%LOCALAPPDATA%\Vocali\vocali.startup_error.log` if booting crashes before the tray comes up.
- Windows: `py build.py --debug` produces a console-mode `.exe` so import errors and COM init failures are visible at runtime.

### Changed

- Windows: heavy imports now run after logging is configured so any `ImportError` is captured to the log file instead of disappearing into the windowed launcher's discarded stderr.

## [0.4.0] - 2026-04-29

### Added

- Windows port (`windows/`): standalone Python implementation with system tray, global hotkeys, Groq Whisper transcription, LLM cleanup, custom vocabulary, and secure API-key storage in Windows Credential Manager.
- Windows: Edit Mode (`Ctrl+Shift+Space` by default) to transform highlighted text by voice.
- Windows: floating recording overlay.
- Windows: UI Automation accessibility-tree context for the cleanup model.
- Windows: run-on-login via the per-user `Run` registry key.
- Windows: auto-update against GitHub Releases.
- Windows: PyInstaller build (`Vocali.exe`, single file) plus a parallel CI job that publishes it to each release tag.

### Changed

- Project renamed from FreeFlow to Vocali.

## [0.3.3] - 2026-04-25

### Added

- Output Language setting for automatically translating dictated text before it is pasted.
- Transcription Language setting for choosing the language Vocali listens for during dictation.
- Recording state flag file for external tools that need to know when Vocali is actively recording.
- Distinct Vocali Dev app and menu bar icons so development builds are easier to tell apart from release builds.

### Improved

- Permission prompts and setup screens now use the correct app name for the installed build.
- Release notes in update prompts now render changelog formatting more clearly.
- Development builds now have clearer bundle naming and icon handling.

### Fixed

- Fixed audio recording crashes caused by unexpected input formats, resampling, and upload-path conversion.
- Fixed cases where Vocali could silently fall back when the selected microphone was unavailable.
- Fixed paste shortcuts on Colemak-DH and other non-QWERTY keyboard layouts.
- Fixed output language handling when custom system prompts are enabled.

## [0.3.2] - 2026-04-23

### Fixed

- Removed the pause-based audio interruption mode that could misfire and resume playback unexpectedly; dictation now only mutes audio.

## [0.3.1] - 2026-04-23

### Added

- Faster live dictation with realtime transcription support.
- A setting for choosing the realtime transcription model.
- Run log exports, so you can save a full dictation run for debugging or sharing.
- A Copy Transcript action in the run log.
- A voice command for submitting text: say "press enter" at the end of a dictation.
- Audio controls that can mute or pause other audio while you dictate, then restore it when recording stops.
- Build details in Settings for easier troubleshooting.
- Direct shortcuts from Vocali to the right macOS permission settings.
- A What’s New popup when an update is available.

### Improved

- Recording feedback now feels more responsive.
- The run log is easier to scan and use.
- Exported run logs include more useful context for reproducing issues.
- Realtime transcription is more reliable when recordings are cancelled, retried, or finish with no text.
- Provider settings are easier to edit without accidental whitespace or half-saved values.
- Vocali now warns you if alert sounds may be hard to hear because system audio is muted or very low.
- Update prompts now show the version, release date, and release notes more clearly.
- Vocali now uses proper version numbers for updates instead of internal build names.

### Fixed

- Fixed cases where arrow or navigation keys could be mistaken for Fn shortcut input.
- Fixed a clipboard timing issue that could paste the wrong content.
- Fixed empty realtime transcriptions getting stuck instead of finishing cleanly.
- Fixed waveform glitches caused by invalid audio levels.
- Filtered out more common transcription artifacts.
- Fixed alert sound hints staying visible after alert sounds are turned off.
- Fixed update checks so users only see real app releases, not internal builds.
- Fixed update checks so the app does not offer an older or already-installed version.
