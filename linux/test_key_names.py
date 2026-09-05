#!/usr/bin/env python3
"""Check that evdev key names actually satisfy the shared combo parser.

This is the seam that breaks silently: `hotkeys.py` matches settings
strings like "ctrl+right alt" against whatever names the key source emits,
and evdev spells things differently from the Windows `keyboard` library.
Run it after touching either side:

    .venv/bin/python linux/test_key_names.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "windows"))

from evdev import ecodes  # noqa: E402

import config  # noqa: E402
import hotkeys  # noqa: E402
from key_source import _key_name  # noqa: E402


def pressed(*codes):
    return {_key_name(c) for c in codes}


def satisfied(combo, keys):
    return hotkeys._all_satisfied(hotkeys._parse(combo), keys)


def _ui_paste_choices():
    """The values offered by the Settings dropdown, read from its source.

    Keeps the UI list and the chord table from drifting apart — a mismatch
    would only show up as a silently ignored setting.
    """
    import re
    source = (HERE.parent / "windows" / "settings_ui.py").read_text()
    match = re.search(r"values=\(([^)]*)\)", source)
    assert match, "paste shortcut dropdown not found in settings_ui.py"
    return re.findall(r'"([a-z+]+)"', match.group(1))


def main():
    assert _key_name(ecodes.KEY_RIGHTALT) == "right alt"
    assert _key_name(ecodes.KEY_LEFTCTRL) == "left ctrl"
    assert _key_name(ecodes.KEY_SPACE) == "space"
    assert _key_name(ecodes.KEY_A) == "a"
    assert _key_name(ecodes.KEY_F5) == "f5"

    # The three shipped defaults must match the keys a real keyboard sends.
    defaults = config.Settings()
    assert satisfied(defaults.hold_shortcut, pressed(ecodes.KEY_RIGHTALT))
    assert satisfied(defaults.toggle_shortcut,
                     pressed(ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTALT))
    assert satisfied(defaults.toggle_shortcut,
                     pressed(ecodes.KEY_RIGHTCTRL, ecodes.KEY_RIGHTALT))
    assert satisfied(defaults.edit_shortcut,
                     pressed(ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT,
                             ecodes.KEY_SPACE))

    # ...and must not fire on near misses.
    assert not satisfied(defaults.hold_shortcut, pressed(ecodes.KEY_LEFTALT))
    assert not satisfied(defaults.toggle_shortcut, pressed(ecodes.KEY_RIGHTALT))
    assert not satisfied(defaults.edit_shortcut,
                         pressed(ecodes.KEY_LEFTCTRL, ecodes.KEY_SPACE))

    # Every offered paste chord must resolve, and junk must fall back to
    # Ctrl+V rather than throwing mid-dictation.
    import paste
    for choice in ("ctrl+v", "ctrl+shift+v", "shift+insert"):
        assert choice in paste._PASTE_CHORDS
    assert set(paste._PASTE_CHORDS) == set(_ui_paste_choices())
    for chord in paste._PASTE_CHORDS.values():
        assert set(chord) <= set(paste._CAPABILITIES[ecodes.EV_KEY]), chord

    # The Linux overlay must actually shadow the Windows modules.
    import auto_start, context_provider, paste, single_instance
    for module in (auto_start, context_provider, paste, single_instance):
        assert Path(module.__file__).parent == HERE, module.__file__
    assert context_provider.context_summary() == ""

    print("key name checks passed")


if __name__ == "__main__":
    main()
