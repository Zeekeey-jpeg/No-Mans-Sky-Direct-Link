"""Find No Man's Sky save files on this machine.

Windows:  %APPDATA%\\HelloGames\\NMS\\<account>\\save*.hg
macOS:    ~/Library/Application Support/HelloGames/NMS/<account>/
Linux:    Steam Proton prefix for app 275850

``<account>`` is ``st_<steamid64>`` for Steam or ``DefaultUser`` for GOG. Slot layout:
``save.hg`` = slot 1 manual, ``save2.hg`` = slot 1 auto, ``save3.hg`` = slot 2 manual, and so on
(odd = manual, even = auto, 15 slots). ``mf_*.hg`` files are encrypted manifests and are skipped.
Set ``NMS_SAVE_DIR`` to point at a specific account folder (or a folder of ``save*.hg`` files).

Xbox / Microsoft Store (Game Pass) saves use the WGS container format and are not supported yet.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SAVE_DIR_ENV = "NMS_SAVE_DIR"
_SAVE_RE = re.compile(r"^save(\d*)\.hg$", re.IGNORECASE)


@dataclass(frozen=True)
class SaveFile:
    path: Path
    slot: int
    kind: str  # "manual" | "auto"
    platform: str  # "steam" | "gog" | "custom" | "unknown"
    account: str
    modified: datetime
    size: int

    @property
    def label(self) -> str:
        return f"slot {self.slot} {self.kind}"

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "slot": self.slot,
            "kind": self.kind,
            "platform": self.platform,
            "account": self.account,
            "modified": self.modified.isoformat(),
            "size_bytes": self.size,
        }


def _platform_of(account_dir: Path) -> str:
    name = account_dir.name
    if name.startswith("st_") and name[3:].isdigit():
        return "steam"
    if name.lower() == "defaultuser":
        return "gog"
    return "unknown"


def default_roots() -> list[Path]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "HelloGames" / "NMS")
    home = Path.home()
    roots.append(home / "Library" / "Application Support" / "HelloGames" / "NMS")
    roots.append(
        home
        / ".local/share/Steam/steamapps/compatdata/275850/pfx/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS"
    )
    roots.append(
        home
        / ".steam/steam/steamapps/compatdata/275850/pfx/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS"
    )
    return roots


def find_save_dirs() -> list[tuple[Path, str]]:
    """Return ``(account_dir, platform)`` pairs that contain at least one ``save*.hg``."""
    env = os.environ.get(SAVE_DIR_ENV)
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            if any(_SAVE_RE.match(f.name) for f in p.iterdir() if f.is_file()):
                plat = _platform_of(p)
                return [(p, plat if plat != "unknown" else "custom")]
            return [(d, _platform_of(d)) for d in sorted(p.iterdir()) if d.is_dir() and _has_saves(d)]
        return []
    found: list[tuple[Path, str]] = []
    for root in default_roots():
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and _has_saves(d):
                found.append((d, _platform_of(d)))
    return found


def _has_saves(d: Path) -> bool:
    try:
        return any(_SAVE_RE.match(f.name) for f in d.iterdir() if f.is_file())
    except OSError:
        return False


def _slot_and_kind(filename: str) -> tuple[int, str]:
    m = _SAVE_RE.match(filename)
    assert m is not None
    n = int(m.group(1) or "1")
    slot = (n + 1) // 2
    kind = "manual" if n % 2 == 1 else "auto"
    return slot, kind


def list_saves() -> list[SaveFile]:
    """All save files on this machine, newest first."""
    out: list[SaveFile] = []
    for account_dir, platform in find_save_dirs():
        for f in account_dir.iterdir():
            if not f.is_file() or not _SAVE_RE.match(f.name):
                continue
            st = f.stat()
            slot, kind = _slot_and_kind(f.name)
            out.append(
                SaveFile(
                    path=f,
                    slot=slot,
                    kind=kind,
                    platform=platform,
                    account=account_dir.name,
                    modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                    size=st.st_size,
                )
            )
    out.sort(key=lambda s: s.modified, reverse=True)
    return out


def newest_save(slot: int | None = None) -> SaveFile | None:
    """Most recently written save, optionally restricted to one slot."""
    saves = list_saves()
    if slot is not None:
        saves = [s for s in saves if s.slot == slot]
    return saves[0] if saves else None
