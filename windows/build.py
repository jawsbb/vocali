"""Bundle Vocali into a single ``Vocali.exe`` using PyInstaller.

Usage:
    py -m pip install -r requirements.txt
    py -m pip install -r requirements-build.txt
    py build.py            # production: --windowed (no console)
    py build.py --debug    # diagnostic: --console (stdout/stderr visible)

Output: ``windows/dist/Vocali.exe``

Use the debug build when troubleshooting "the .exe runs but nothing
happens" — the console will show import errors, COM init failures,
and any other startup exception that the windowed launcher swallows.
"""

from __future__ import annotations

import argparse
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
VERSION_TEMPLATE = HERE / "version_info_template.txt"
VERSION_FILE = HERE / "version_info.generated.txt"


# Modules PyInstaller's static analysis can miss because they're loaded
# through dynamic imports inside the dependency packages.
HIDDEN_IMPORTS = [
    "pystray._win32",
    "PIL._tkinter_finder",
    "keyring.backends.Windows",
    "win32timezone",  # pulled in by some keyring backends
    "uiautomation",
    "comtypes.gen",  # uiautomation generates COM stubs into here at runtime
]

# Packages whose data files (themes, .tcl, etc.) need to ship alongside
# the .py modules. ``--collect-all`` bundles modules + binaries + data.
COLLECT_ALL = [
    "sv_ttk",  # ships sv.tcl + theme/ folder of Tcl theme files
]


def _read_version() -> str:
    sys.path.insert(0, str(HERE))
    try:
        import version  # type: ignore
        return version.VERSION
    finally:
        sys.path.pop(0)


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts: list[int] = []
    for chunk in version.lstrip("vV").split(".")[:4]:
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def _generate_version_file(version: str) -> Path:
    if not VERSION_TEMPLATE.exists():
        return Path()
    template = VERSION_TEMPLATE.read_text(encoding="utf-8")
    tup = _version_tuple(version)
    rendered = (
        template
        .replace("{{filevers}}", repr(tup))
        .replace("{{prodvers}}", repr(tup))
        .replace("{{version_str}}", ".".join(str(n) for n in tup))
    )
    VERSION_FILE.write_text(rendered, encoding="utf-8")
    return VERSION_FILE


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Vocali.exe with PyInstaller.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build with --console instead of --windowed for live error output.",
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        print("build.py must run on Windows.", file=sys.stderr)
        return 1
    if not ENTRY.exists():
        print(f"Entry not found: {ENTRY}", file=sys.stderr)
        return 1

    # Clean previous artifacts so PyInstaller starts from a known state.
    for path in (DIST, BUILD, SPEC, VERSION_FILE):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    version = _read_version()
    mode = "DEBUG (console)" if args.debug else "release (windowed)"
    print(f"Building Vocali v{version} — {mode}…")
    version_file = _generate_version_file(version)

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "Vocali",
        "--onefile",
        "--console" if args.debug else "--windowed",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(HERE),
    ]
    if ICON.exists():
        cmd += ["--icon", str(ICON)]
    if version_file and version_file.exists():
        # Embeds VS_VERSIONINFO so the OS / Defender see CompanyName,
        # ProductName, ProductVersion etc. — reduces (but doesn't eliminate)
        # PyInstaller-bundle false positives on unsigned builds.
        cmd += ["--version-file", str(version_file)]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    cmd.append(str(ENTRY))

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(HERE))
    if proc.returncode != 0:
        return proc.returncode

    out = DIST / "Vocali.exe"
    if out.exists():
        print(f"\nBuilt {out} ({out.stat().st_size / (1024*1024):.1f} MB)")
        if args.debug:
            print("Debug build: run from a terminal (cmd, PowerShell) to see live output.")
    else:
        print("PyInstaller finished but Vocali.exe was not produced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
