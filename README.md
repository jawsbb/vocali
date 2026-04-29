<p align="center">
  <img src="Resources/AppIcon-Source.png" width="128" height="128" alt="Vocali icon">
</p>

<h1 align="center">Vocali</h1>

<p align="center">
  Free and open source dictation app for <b>macOS and Windows</b>.<br>
  Inspired by <a href="https://wisprflow.ai">Wispr Flow</a>, <a href="https://superwhisper.com">Superwhisper</a>, and <a href="https://monologue.to">Monologue</a>.
</p>

<p align="center">
  <i>Fork of <a href="https://github.com/zachlatta/freeflow">FreeFlow</a> by <a href="https://github.com/zachlatta">Zach Latta</a>, with a Windows port added.</i>
</p>

---

## Overview

Vocali is a free dictation app. Hold a hotkey, talk, release — your speech is transcribed by Groq Whisper and (optionally) cleaned up by an LLM, then pasted into the focused text field.

It runs as a tray / menu bar app on both macOS and Windows. There is no Vocali server: the only data leaving your computer are API calls to your configured transcription and LLM provider.

## Quick start

You'll need a free Groq API key from [console.groq.com](https://console.groq.com/keys).

### macOS

Build from source (Swift, native menu-bar app):

```bash
make run
```

See [Building macOS](#building-macos) for details, signing, and DMG packaging.

Default shortcuts on macOS: hold **`Fn`** to talk, or tap **`⌘-Fn`** to toggle.

### Windows

The Windows version is a separate from-scratch port written in Python. Lives in [`windows/`](windows/).

**Easiest:** download `Vocali.exe` from the [latest release](https://github.com/jawsbb/vocali/releases/latest), run it. Right-click the tray icon → Settings → paste your Groq API key.

**From source** (if you want to modify it):

```powershell
cd windows
py -m pip install -r requirements.txt
py vocali.py
```

Default shortcuts on Windows: hold **`Right Alt`** to talk, or tap **`Ctrl + Right Alt`** to toggle. (`Fn` cannot be intercepted on most Windows keyboards.) An optional **`Ctrl + Shift + Space`** Edit Mode lets you transform the selected text by voice ("make this shorter", "translate to French"). Settings has a **Run on login** toggle.

See [`windows/README.md`](windows/README.md) for details and build instructions.

## Features

- **Custom shortcuts** — customize both hold-to-talk and toggle dictation shortcuts.
- **Custom vocabulary** — add names, jargon, project-specific words to preserve during cleanup.
- **Context-aware cleanup** *(macOS only for now)* — reads nearby app context so names and terms are spelled correctly when you dictate into email, terminals, docs, etc.
- **Edit Mode** *(macOS only for now)* — highlight text, hold the shortcut, and say "make this shorter" / "turn this into bullets" to transform it.
- **OpenAI-compatible providers** — use Groq by default, or configure a custom model and API URL in settings.

Windows parity: hotkeys, transcription, LLM cleanup, vocabulary, custom prompt, tray UI, **Edit Mode**, **recording overlay**, **UI Automation accessibility context**, **run-on-login**, **auto-update from GitHub Releases**, and a **single-file `Vocali.exe` build** are all in.

## Privacy

Vocali does not have a server. The only outbound traffic is API calls to your transcription and LLM provider (Groq by default). API keys are stored in the system keychain (macOS Keychain / Windows Credential Manager), never in plain text.

## Building macOS

```bash
make run                          # build a Dev bundle and launch it
make all APP_NAME=Vocali           # build the release bundle
make dmg APP_NAME=Vocali           # produce a DMG
```

Set `CODESIGN_IDENTITY` to your Developer ID for signed builds. The release workflow in [`.github/workflows/release.yml`](.github/workflows/release.yml) handles signing, notarization, and DMG upload when you push a `v*.*.*` tag.

## Custom Cleanup

If you'd rather keep cleanup more literal and less context-aware, you can paste this simpler prompt into the custom system prompt setting:

<details>
  <summary>Simple post-processing prompt</summary>

  <pre><code>You are a dictation post-processor. You receive raw speech-to-text output and return clean text ready to be typed into an application.

Your job:
- Remove filler words (um, uh, you know, like) unless they carry meaning.
- Fix spelling, grammar, and punctuation errors.
- When the transcript already contains a word that is a close misspelling of a name or term from the context or custom vocabulary, correct the spelling. Never insert names or terms from context that the speaker did not say.
- Preserve the speaker's intent, tone, and meaning exactly.

Output rules:
- Return ONLY the cleaned transcript text, nothing else. So NEVER output words like "Here is the cleaned transcript text:"
- If the transcription is empty, return exactly: EMPTY
- Do not add words, names, or content that are not in the transcription. The context is only for correcting spelling of words already spoken.
- Do not change the meaning of what was said.</code></pre>
</details>

## Credits

Vocali is a fork of [FreeFlow](https://github.com/zachlatta/freeflow) by [Zach Latta](https://github.com/zachlatta), with a Windows port added by [Jules Koehler](https://github.com/jawsbb).

Original FreeFlow contributors are credited in the upstream repo. The macOS app source code in [`Sources/`](Sources/) is the FreeFlow Swift codebase with rebranding.

## License

MIT — see [LICENSE](LICENSE). Original FreeFlow copyright is preserved.
