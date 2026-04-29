"""Check GitHub Releases for a newer Vocali build.

This is the Windows equivalent of the Mac app's UpdateManager.swift. It is a
**check + notify** updater, not a self-replacing one. Replacing the running
.exe on Windows requires a separate helper process (the running .exe holds
its own file handle), which is more risk than reward for a small project. We
just point the user at the GitHub release so they can grab the new .exe.

Anonymous GitHub API access is rate-limited to 60 req/hour per IP. We cache
the result in memory; the main app spaces checks at most once per startup
plus on user-initiated clicks.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


GITHUB_API = "https://api.github.com/repos/jawsbb/vocali/releases/latest"
USER_AGENT = "Vocali-Windows-Updater"
DEFAULT_TIMEOUT = 8.0


@dataclass(frozen=True)
class UpdateInfo:
    version: str        # without leading "v", e.g. "0.4.1"
    name: str           # release title
    body: str           # release notes (markdown)
    download_url: str   # direct .exe asset download (may be empty if missing)
    html_url: str       # github.com/jawsbb/vocali/releases/tag/...


def _parse_version(value: str) -> tuple[int, ...]:
    s = (value or "").lstrip("vV").strip()
    if not s:
        return ()
    parts: list[int] = []
    for chunk in s.split(".")[:3]:
        try:
            parts.append(int(chunk))
        except ValueError:
            return ()
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    a = _parse_version(latest)
    b = _parse_version(current)
    if not a or not b:
        return False
    return a > b


def check_for_update(
    current_version: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> UpdateInfo | None:
    """Return UpdateInfo if a newer release is available, else None.

    Returns None on any network/parse error — callers should treat it as
    "no update right now" rather than surface the failure.
    """
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    tag = (data.get("tag_name") or "").strip()
    if not tag or not is_newer(tag, current_version):
        return None

    download_url = ""
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = (asset.get("name") or "").lower()
        if name == "vocali.exe":
            download_url = asset.get("browser_download_url") or ""
            break

    return UpdateInfo(
        version=tag.lstrip("vV"),
        name=(data.get("name") or tag),
        body=(data.get("body") or ""),
        download_url=download_url,
        html_url=(data.get("html_url") or ""),
    )
