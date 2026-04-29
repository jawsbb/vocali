"""Bundle Vocali into a single ``Vocali.exe`` using PyInstaller.

Usage:
    py -m pip install -r requirements.txt
    py -m pip install -r requirements-build.txt
    py build.py

Output: ``windows/dist/Vocali.exe``
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ENTRY = HERE / "vocali.py"
ICON = HERE / "Vocali.ico"
DIST = HERE / "dist"
BUILD = HERE / "build"
SPEC = HERE / "Vocali.spec"


# Modules PyInstaller's static analysis can miss because they're loaded
# through dynamic imports inside the dependency packages.
HIDDEN_IMPORTS = [
    "pystray._win32",
    "PIL._tkinter_finder",
    "keyring.backends.Windows",
    "win32timezone",  # pulled in by some keyring backends
]


def main() -> int:
    if sys.platform != "win32":
        print("build.py must run on Windows.", file=sys.stderr)
        return 1
    if not ENTRY.exists():
        print(f"Entry not found: {ENTRY}", file=sys.stderr)
        return 1

    # Clean previous artifacts so PyInstaller starts from a known state.
    for path in (DIST, BUILD, SPEC):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "Vocali",
        "--onefile",
        "--windowed",  # no console window on launch
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(HERE),
    ]
    if ICON.exists():
        cmd += ["--icon", str(ICON)]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    cmd.append(str(ENTRY))

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(HERE))
    if proc.returncode != 0:
        return proc.returncode

    out = DIST / "Vocali.exe"
    if out.exists():
        print(f"\nBuilt {out} ({out.stat().st_size / (1024*1024):.1f} MB)")
    else:
        print("PyInstaller finished but Vocali.exe was not produced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
