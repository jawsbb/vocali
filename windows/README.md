# Vocali for Windows

A Windows port of [Vocali](https://github.com/jawsbb/vocali) — free dictation app with Groq Whisper transcription and optional LLM cleanup.

## Two ways to install

### Option A — `Vocali.exe` (recommended)

1. Download `Vocali.exe` from the [latest release](https://github.com/jawsbb/vocali/releases/latest).
2. Run it. A waveform icon appears in the system tray.
3. Right-click the tray icon → **Settings** → paste your free [Groq API key](https://console.groq.com/keys) → **Save**.
4. Hold `Right Alt` and speak.

The single-file build is ~33 MB. No Python install required.

### Option B — Run from source

If you prefer to run the Python source directly (e.g. you want to modify it):

1. Install Python 3.10+ if you don't have it.
2. From this `windows/` folder:
   ```
   py -m pip install -r requirements.txt
   py vocali.py
   ```

## Default shortcuts

- **Hold `Right Alt`** to talk. Release to transcribe and paste.
- **Tap `Ctrl + Right Alt`** to toggle (start / stop) dictation hands-free.
- **Hold `Ctrl + Shift + Space`** with text selected to enter Edit Mode: speak a transformation ("make this shorter", "translate to French", "turn into bullets"), release, and the selected text gets replaced.

You can change all three shortcuts in Settings. The Mac app uses the `Fn` key — Windows does not let user code intercept `Fn`, so the default is `Right Alt` instead.

## Run on login

Open Settings → tick **Start Vocali automatically when I sign in to Windows** → Save.

This writes a value under `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` (per-user, no admin needed). When running from source, it points at `pythonw.exe` (no console window flashes on login). When running from the bundled `.exe`, it points at the `.exe` directly. Untick to remove.

## Updates

Vocali checks GitHub Releases for a newer version 20 seconds after startup (toggle off in Settings → Updates). If one is available you'll see an "Update to vX.Y.Z" item in the tray menu — clicking it opens the GitHub release page so you can download the new `Vocali.exe`. The tray menu also has **Check for updates…** for an on-demand check.

The current version is in [`version.py`](version.py); bump it before tagging a release.

This is a check-and-notify updater — Vocali does not auto-replace the running `.exe` (Windows holds the file open while the process runs, so an in-place swap needs a separate helper process; not worth the complexity for now).

## How dictation works

1. You hold the hotkey and speak.
2. Audio is sent to Groq's `whisper-large-v3` for transcription.
3. *(Optional)* A second Groq LLM call cleans up filler words, fixes punctuation, etc. The foreground window's title is sent as lightweight context so the cleanup model can spell names correctly.
4. The cleaned text is copied to the clipboard and pasted into the focused app via simulated `Ctrl+V`.

## How Edit Mode works

1. Highlight some text in any app.
2. Hold the Edit shortcut.
3. Speak the change you want: *"make this shorter"*, *"turn into a numbered list"*, *"translate to Spanish"*, *"fix the grammar"*.
4. Release. Vocali captures the selection via simulated `Ctrl+C`, transcribes your command, asks the LLM to transform the selection, and pastes the result over the selection.
5. Your previous clipboard contents are restored after the paste.

If no text is selected when you press the Edit shortcut, Vocali ignores it.

## Building `Vocali.exe` yourself

```
py -m pip install -r requirements.txt
py -m pip install -r requirements-build.txt
py build.py
```

Output: `dist/Vocali.exe`.

`build.py` calls PyInstaller with `--onefile --windowed`, embeds [Vocali.ico](Vocali.ico), and force-includes the few hidden imports that PyInstaller's static analysis misses (`pystray._win32`, `keyring.backends.Windows`, etc.). The `dist/` folder and the generated `Vocali.spec` are gitignored.

## Notes vs. the Mac version

This is a from-scratch port — it does not share code with the Swift app. Parity with the Mac version:

- [x] Hold-to-talk and tap-to-toggle hotkeys
- [x] Groq Whisper transcription
- [x] LLM post-processing with the same default system prompt
- [x] Custom vocabulary and custom system prompt
- [x] Custom OpenAI-compatible base URL / model
- [x] Secure API key storage (Windows Credential Manager via `keyring`)
- [x] System tray icon
- [x] **Edit Mode** (transform highlighted text via voice command)
- [x] **Floating recording overlay**
- [x] **Lightweight foreground-window context** (title + executable name)
- [x] **Run on login** (per-user `Run` registry key)
- [x] **Single-file `.exe` distribution** (PyInstaller)
- [x] **Auto-update** — checks GitHub Releases on startup, surfaces updates in the tray menu
- [x] **UI Automation context** — walks the focused app's accessibility tree to feed the cleanup model with surrounding text (recipient names, email subject, chat thread, IDE breadcrumbs). Captured in parallel with recording start so the user's first words aren't lost.

## Files

- `vocali.py` — entry point, wires everything together
- `audio_recorder.py` — microphone capture (sounddevice → in-memory WAV)
- `hotkeys.py` — global hotkey hook (hold + toggle + edit combos)
- `transcription.py` — Groq Whisper API client
- `postprocessing.py` — Groq chat-completions client (cleanup + edit transform)
- `paste.py` — clipboard + simulated Ctrl+V/Ctrl+C via Win32 SendInput
- `context_provider.py` — foreground-window title/exe via Win32 GetForegroundWindow
- `recording_overlay.py` — small floating Tk window shown while recording
- `auto_start.py` — read/write the `HKCU\…\Run` registry value
- `updater.py` — checks GitHub Releases for a newer version
- `version.py` — single source of truth for the app version
- `settings_ui.py` — Tkinter Settings dialog
- `config.py` — JSON settings + Windows Credential Manager for API key
- `build.py` — PyInstaller wrapper that produces `dist/Vocali.exe`
- `Vocali.ico` — Windows app icon
