# Vocali for Linux

A Linux port of [Vocali](https://github.com/jawsbb/vocali) — free dictation app
with Groq Whisper transcription and optional LLM cleanup.

It shares its logic with the [Windows port](../windows): this folder only holds
the five modules that have to differ per OS (global hotkeys, paste, autostart,
single-instance, window context). `linux/vocali` puts this directory ahead of
`../windows` on `sys.path`, so those names shadow their Windows twins and
everything else is the same code.

Tested on Fedora 44 / KDE Plasma 6 / Wayland. Should work on any X11 or Wayland
desktop that has a StatusNotifierItem tray (GNOME needs the AppIndicator
extension).

## Install

```bash
# 1. System packages
sudo dnf install python3-evdev libayatana-appindicator-gtk3 \
                python3-gobject python3-cairo wl-clipboard
#   Debian/Ubuntu: sudo apt install python3-evdev gir1.2-ayatanaappindicator3-0.1 \
#                    python3-gi python3-gi-cairo wl-clipboard
#   X11 instead of Wayland: replace wl-clipboard with xclip

# 2. Read access to the keyboard (see "Why /dev/input" below)
sudo usermod -aG input "$USER"
#   Log out and back in — a new terminal is not enough.

# 3. Python deps
cd linux
python3 -m venv --system-site-packages .venv   # system packages = python3-evdev + GTK bindings
.venv/bin/pip install -r requirements.txt

# 4. Run
.venv/bin/python ./vocali
```

A waveform icon appears in the system tray. On the first run the Settings
window opens by itself so you can paste your free
[Groq API key](https://console.groq.com/keys) → **Save**.

## Default shortcuts

- **Hold `Right Alt`** to talk. Release to transcribe and paste.
- **Tap `Ctrl + Right Alt`** to toggle dictation hands-free.
- **Hold `Ctrl + Shift + Space`** with text selected to enter Edit Mode: speak a
  transformation ("make this shorter", "translate to French"), release, and the
  selection gets replaced.

All three are editable in Settings. The Mac app uses `Fn`; on Linux `Fn` is
usually handled in keyboard firmware and never reaches the kernel, so the
default is `Right Alt`.

## Run on login

Settings → tick **Start Vocali automatically when I sign in** → Save. That writes
`~/.config/autostart/vocali.desktop` pointing at the interpreter you launched
with, so a venv install keeps working. Move or rename the checkout and the entry
goes stale — untick and retick to rewrite it.

If Vocali can't start (no `input` group yet, no `/dev/uinput`) it says so with a
desktop notification as well as on stderr, because nothing launched from
`autostart` has a terminal to print to.

## Why /dev/input and /dev/uinput

Wayland deliberately stops applications from seeing keys pressed in other
windows or typing into them. Vocali needs both, so it goes below the
compositor:

- **Reading hotkeys** — `/dev/input/event*` via evdev. Only members of the
  `input` group can read it, hence the `usermod` above. This is also why
  hold-to-talk works at all: compositor shortcut APIs (KGlobalAccel, portals)
  report a key press but not its release.
- **Pasting** — a virtual keyboard on `/dev/uinput`, which the compositor sees
  as an ordinary USB keyboard. systemd normally grants the logged-in user an
  ACL on it automatically. If `./vocali` says it can't write there:

  ```bash
  echo 'KERNEL=="uinput", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-uinput.rules
  sudo udevadm control --reload && sudo udevadm trigger
  ```

Nothing runs as root and no daemon is installed.

## Differences from the Windows port

| | Windows | Linux |
|---|---|---|
| Hotkeys | `keyboard` lib (Win32 hook) | evdev on `/dev/input` |
| Paste | `SendInput` | virtual keyboard on `/dev/uinput` |
| Clipboard | `pyperclip` | `wl-copy` / `xclip` |
| API key | Credential Manager | KWallet / GNOME Keyring (via `keyring`) |
| Run on login | `HKCU\…\Run` | `~/.config/autostart` |
| Settings | `%APPDATA%\Vocali` | `~/.config/vocali` |
| Logs | `%LOCALAPPDATA%\Vocali` | `~/.local/state/Vocali` |
| Window context | UI Automation tree | **not available** — see below |

**No window context.** The Windows port sends the focused app's title and
surrounding accessibility text to the cleanup model so it can spell names
right. Wayland exposes neither. AT-SPI could in principle, but on a stock
desktop only the shell's own helpers register with it — apps opt in only when
accessibility is enabled system-wide. The `use_window_context` setting is a
no-op here; cleanup just runs without it.

**Paste shortcut is a setting, not a guess.** Terminals ignore `Ctrl+V` and want
`Ctrl+Shift+V`; browsers and editors want `Ctrl+V`. Knowing which app has focus
would need the window info we just said we can't get, so Settings → Shortcuts →
**Paste** lets you choose (`ctrl+v`, `ctrl+shift+v`, `shift+insert`). Pick the
one matching where you dictate most.

**No single-file bundle.** Run from source. PyInstaller on Linux produces a
binary tied to the glibc it was built against, which is a worse deal than a
`dnf install` plus a venv.

## Troubleshooting

Logs go to `~/.local/state/Vocali/vocali.log`.

- **Nothing happens on the hotkey** — check the log for "Listening on
  keyboard:" lines. None means the `input` group didn't take effect; log out and
  back in, and confirm with `id | grep input`. Keyboards are re-scanned every
  five seconds, so one that slept or was replugged comes back on its own.
- **No tray icon** — `libayatana-appindicator-gtk3` is missing, or your desktop
  has no SNI host. Vocali still works; open Settings by restarting it with no
  API key set, or edit `~/.config/vocali/settings.json` directly.
- **Transcript appears in the wrong window** — the paste fires ~1 s after you
  release the key, so don't click away while it's transcribing.

## Files

Linux-specific:

- `vocali` — launcher: preflight checks, `sys.path` overlay, then the shared app
- `key_source.py` — global key events from `/dev/input` via evdev
- `paste.py` — clipboard (`wl-copy`/`xclip`) + `Ctrl+V` through `/dev/uinput`
- `auto_start.py` — `~/.config/autostart/vocali.desktop`
- `recording_overlay.py` — the macOS-style pill: GTK3 + Cairo, live waveform
- `notify.py` — desktop notifications via `notify-send` (pystray has none here)
- `single_instance.py` — abstract-unix-socket guard against a double launch
- `context_provider.py` — stub, see above
- `test_key_names.py` — checks evdev key names still satisfy the combo parser

Everything else (`config`, `audio_recorder`, `transcription`, `postprocessing`,
`hotkeys`, `settings_ui`, `updater`, `theme`) comes from
[`../windows/`](../windows).

## Recording overlay

Ported from the Mac app's `RecordingOverlay.swift`: a black pill hanging from
the top edge of whichever monitor the pointer is on, sliding down on appear.
Three states — cycling dots while the mic warms up, nine capsule bars driven by
the live microphone level, then sine-driven bars while the transcript is in
flight.

It is drawn with GTK3 and Cairo rather than Tk, for one reason: rounded
corners. Tk on X11 has no per-pixel alpha, and the X SHAPE extension does not
substitute for it — XWayland keeps the surface rectangular and paints the
clipped-away region black rather than transparent. A GTK window on an RGBA
visual gets real alpha, which KWin composites correctly, and Cairo
anti-aliases the capsule bars for free.

That is also why `linux/vocali` pins `GDK_BACKEND=x11`: Wayland forbids a
client from positioning its own windows, and this one has to sit at a chosen
spot. The tray is unaffected — StatusNotifierItem rides on D-Bus.

The overlay has no main loop of its own. pystray's tray already runs
`Gtk.main()` on the main thread, and a second GTK loop on a second thread
would be a crash waiting to happen, so state changes hop onto that loop via
`GLib.idle_add`.

A monitor is picked from the pointer position: the union of a portrait panel
and a landscape one has a centre that lands in the dead space between them.
