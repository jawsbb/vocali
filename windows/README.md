# Vocali for Windows

A Windows port of [Vocali](https://github.com/jawsbb/vocali) — free dictation app with Groq Whisper transcription and optional LLM cleanup.

## Install

1. Install Python 3.10+ if you don't have it.
2. From this `windows/` folder, install dependencies:
   ```
   py -m pip install -r requirements.txt
   ```
3. Get a free Groq API key at https://console.groq.com/keys

## Run

```
py vocali.py
```

A waveform icon appears in the system tray. Right-click it and pick **Settings** the first time to paste your Groq API key.

## Default shortcuts

- **Hold `Right Alt`** to talk. Release to transcribe and paste.
- **Tap `Ctrl + Right Alt`** to toggle (start / stop) dictation hands-free.
- **Hold `Ctrl + Shift + Space`** with text selected to enter Edit Mode: speak a transformation ("make this shorter", "translate to French", "turn into bullets"), release, and the selected text gets replaced.

You can change all three shortcuts in Settings. The Mac app uses the `Fn` key — Windows does not let user code intercept `Fn`, so the default is `Right Alt` instead.

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
- [ ] Full UI Automation context (full app accessibility tree) — Mac uses the macOS Accessibility API; Windows MVP only sends the window title

## Files

- `vocali.py` — entry point, wires everything together
- `audio_recorder.py` — microphone capture (sounddevice → in-memory WAV)
- `hotkeys.py` — global hotkey hook (hold + toggle + edit combos)
- `transcription.py` — Groq Whisper API client
- `postprocessing.py` — Groq chat-completions client (cleanup + edit transform)
- `paste.py` — clipboard + simulated Ctrl+V/Ctrl+C via Win32 SendInput
- `context_provider.py` — foreground-window title/exe via Win32 GetForegroundWindow
- `recording_overlay.py` — small floating Tk window shown while recording
- `settings_ui.py` — Tkinter Settings dialog
- `config.py` — JSON settings + Windows Credential Manager for API key
