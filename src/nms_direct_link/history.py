"""Session history: a compact summary of each distinct save, kept in your user cache folder.

This is the one thing the server writes, and it never touches the game folder or your saves.
Each time a new save is loaded, one JSON line is appended to
``<user cache>/nms-direct-link/history.jsonl`` (Windows: ``%LOCALAPPDATA%``). That lets your
assistant answer "what changed since last session" and track progress over time.
Disable with ``NMS_NO_HISTORY=1``; delete the file at any time.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .save.mapping import user_cache_dir
from .save.model import SaveSnapshot

HISTORY_ENV = "NMS_NO_HISTORY"
HISTORY_DIR_ENV = "NMS_HISTORY_DIR"
MAX_LINES = 500


def history_path() -> Path:
    base = os.environ.get(HISTORY_DIR_ENV)
    return (Path(base) if base else user_cache_dir()) / "history.jsonl"


def enabled() -> bool:
    return os.environ.get(HISTORY_ENV, "").strip() not in ("1", "true", "yes")


def summarise(snap: SaveSnapshot) -> dict[str, Any]:
    items: dict[str, int] = {}
    tech: set[str] = set()
    for inv in snap.inventories():
        for s in inv.slots:
            if s.kind == "Technology":
                tech.add(s.id)
            else:
                items[s.id] = items.get(s.id, 0) + s.amount
    backlog = snap.discovery_backlog()
    systems = {d.address.system_key() for d in snap.discoveries()}
    return {
        "recorded": datetime.now(tz=UTC).isoformat(),
        "save_modified": snap.modified.isoformat() if snap.modified else None,
        "save_account": snap.path.parent.name if snap.path else None,
        "play_seconds": snap.play_time_seconds,
        "units": snap.units, "nanites": snap.nanites, "quicksilver": snap.quicksilver,
        "location": snap.address.portal(),
        "discoveries": backlog["total_records"], "pending_upload": backlog["pending_upload"],
        "systems_known": len(systems), "bases": len(snap.bases()), "frigates": len(snap.frigates()),
        "ships": len(snap.ships()), "known_products": snap.known()["products"],
        "known_tech": len(snap.known()["technology_ids"]),
        "tech": sorted(tech), "items": items,
    }


def read_history(account: str | None = None) -> list[dict[str, Any]]:
    p = history_path()
    if not p.is_file():
        return []
    out = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if account is None or row.get("save_account") == account:
            out.append(row)
    return out


def record(snap: SaveSnapshot) -> dict[str, Any] | None:
    """Append a summary if this save differs from the last recorded one. Returns the row or None."""
    if not enabled():
        return None
    row = summarise(snap)
    rows = read_history(row["save_account"])
    if rows and rows[-1].get("save_modified") == row["save_modified"]:
        return None
    p = history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    all_rows = read_history()
    all_rows.append(row)
    p.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in all_rows[-MAX_LINES:]) + "\n", encoding="utf-8")
    return row


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    num = {}
    for k in ("units", "nanites", "quicksilver", "discoveries", "pending_upload", "systems_known", "bases", "frigates",
              "ships", "known_products", "known_tech"):
        a, b = old.get(k, 0) or 0, new.get(k, 0) or 0
        if a != b:
            num[k] = {"before": a, "after": b, "change": b - a}
    oi, ni = old.get("items", {}), new.get("items", {})
    item_changes = {}
    for k in set(oi) | set(ni):
        d = ni.get(k, 0) - oi.get(k, 0)
        if d:
            item_changes[k] = d
    top_items = sorted(item_changes.items(), key=lambda kv: -abs(kv[1]))[:25]
    ot, nt = set(old.get("tech", [])), set(new.get("tech", []))
    return {
        "from": old.get("save_modified"), "to": new.get("save_modified"),
        "played_minutes": round(((new.get("play_seconds") or 0) - (old.get("play_seconds") or 0)) / 60),
        "moved": old.get("location") != new.get("location"), "from_location": old.get("location"), "to_location": new.get("location"),
        "changes": num, "items_changed": dict(top_items),
        "tech_added": sorted(nt - ot), "tech_removed": sorted(ot - nt),
    }
