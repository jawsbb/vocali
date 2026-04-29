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

You can change both shortcuts in Settings. The Mac app uses the `Fn` key — Windows does not let user code intercept `Fn`, so the default is `Right Alt` instead.

## What it does

1. You hold the hotkey and speak.
2. Audio is sent to Groq's `whisper-large-v3` for transcription.
3. (Optional) A second Groq LLM call cleans up filler words, fixes punctuation, etc.
4. The cleaned text is copied to the clipboard and pasted into the focused app via simulated `Ctrl+V`.

## Notes vs. the Mac version

This is a from-scratch port — it does not share code with the Swift app. Parity with the Mac version:

- [x] Hold-to-talk and tap-to-toggle hotkeys
- [x] Groq Whisper transcription
- [x] LLM post-processing with the same default system prompt
- [x] Custom vocabulary
- [x] Custom OpenAI-compatible base URL / model
- [x] Secure API key storage (Windows Credential Manager via `keyring`)
- [x] System tray icon
- [ ] Context-aware cleanup (would need UI Automation — not implemented yet)
- [ ] Edit Mode (transform highlighted text) — not implemented yet
- [ ] Recording overlay window — not implemented yet
