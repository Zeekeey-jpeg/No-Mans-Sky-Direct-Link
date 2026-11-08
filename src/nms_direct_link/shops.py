"""Shop Scanner: dock, open a merchant, ask "what's here?".

The game never writes a merchant's stock into the save, so this reads the screen instead, the
same way you would. Two ways in:

* ``capture_game_window`` grabs the No Man's Sky window (or the whole screen) right now.
* ``recent_steam_screenshots`` picks up screenshots you took in game with Steam's F12 key, so
  you never have to alt-tab: press F12 at each shop, then ask once.

Your AI assistant reads the image (it is multimodal) and records what it saw with ``log_shop``.
Observations are tied to the system you are in according to the save, and live in a small SQLite
file in your user cache folder, so later you can ask "which station had an S-class hyperdrive
module under 600 nanites?" from anywhere.

Nothing here touches the game process. Capture is the same as a screenshot tool or OBS.
"""

from __future__ import annotations

import contextlib
import ctypes
import io
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .history import history_path
from .save.address import UniverseAddress

MAX_WIDTH = 1600
STEAM_APP_ID = "275850"
SHOP_DB_ENV = "NMS_SHOP_DB"

MERCHANTS = [
    "technology merchant", "starship outfitter", "exosuit merchant", "multi-tool merchant", "exocraft merchant",
    "galactic trade terminal", "scrap dealer", "contraband dealer", "mission board", "trader npc", "quicksilver companion",
    "other",
]


# --------------------------------------------------------------------------- capture


@dataclass
class Shot:
    data: bytes
    width: int
    height: int
    source: str
    taken: float


def _encode(img, max_width: int = MAX_WIDTH) -> tuple[bytes, int, int]:
    from PIL import Image

    img = img.convert("RGB")
    if img.width > max_width:
        h = round(img.height * max_width / img.width)
        img = img.resize((max_width, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), img.width, img.height


def _find_game_window() -> tuple[int, int, int, int] | None:
    """Screen rectangle of the No Man's Sky window on Windows, or None."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.strip().lower() == "no man's sky":
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(enum, 0)
    if not found:
        return None
    import ctypes.wintypes as wt

    rect = wt.RECT()
    user32.GetWindowRect(found[0], ctypes.byref(rect))
    if rect.right - rect.left < 200 or rect.bottom - rect.top < 200:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def capture_game_window(target: str = "game", max_width: int = MAX_WIDTH) -> Shot:
    """Grab the game window only. Captures every screen only for an explicit target="screen". Raises RuntimeError if the window is missing or capture fails."""
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover - Pillow is a dependency
        raise RuntimeError("Pillow is required for screen capture") from exc
    bbox = None
    if target == "game":
        bbox = _find_game_window()
        if bbox is None:
            raise RuntimeError("No Man's Sky window not found (not running, minimized, or exclusive fullscreen). "
                               "Use target='screen' to capture everything on purpose, or press F12 in game and use nms_read_screenshots")
    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=bbox is None)
    except OSError as exc:
        raise RuntimeError(f"screen capture failed: {exc}") from exc
    data, w, h = _encode(img, max_width)
    return Shot(data=data, width=w, height=h, source="game window" if bbox else "all screens", taken=time.time())


def steam_screenshot_dirs() -> list[Path]:
    roots = []
    pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    roots.append(Path(pf86) / "Steam" / "userdata")
    roots.append(Path.home() / ".local/share/Steam/userdata")
    roots.append(Path.home() / "Library/Application Support/Steam/userdata")
    extra = os.environ.get("NMS_SCREENSHOT_DIR")
    if extra:
        p = Path(extra)
        return [p] if p.is_dir() else []
    out: list[Path] = []
    for r in roots:
        if r.is_dir():
            for user in r.iterdir():
                d = user / "760" / "remote" / STEAM_APP_ID / "screenshots"
                if d.is_dir():
                    out.append(d)
    return out


def recent_steam_screenshots(limit: int = 4, within_minutes: float | None = 120, max_width: int = MAX_WIDTH) -> list[Shot]:
    files: list[Path] = []
    for d in steam_screenshot_dirs():
        files += [f for f in d.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    cutoff = time.time() - within_minutes * 60 if within_minutes else 0
    files = [f for f in files if f.stat().st_mtime >= cutoff][:limit]
    from PIL import Image

    shots = []
    for f in files:
        with Image.open(f) as img:
            data, w, h = _encode(img, max_width)
        shots.append(Shot(data=data, width=w, height=h, source=f.name, taken=f.stat().st_mtime))
    return shots


# --------------------------------------------------------------------------- storage


def db_path() -> Path:
    env = os.environ.get(SHOP_DB_ENV)
    return Path(env) if env else history_path().parent / "shops.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seen_at REAL NOT NULL,
  packed INTEGER NOT NULL,
  portal TEXT NOT NULL,
  galaxy INTEGER NOT NULL,
  station TEXT,
  merchant TEXT NOT NULL,
  economy TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS items (
  visit_id INTEGER NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  item_class TEXT,
  category TEXT,
  price REAL,
  currency TEXT,
  quantity INTEGER,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS items_name ON items(name);
CREATE INDEX IF NOT EXISTS visits_packed ON visits(packed);
"""


def connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def log_shop(address: UniverseAddress, merchant: str, items: list[dict[str, Any]], station: str | None = None,
             economy: str | None = None, note: str | None = None, replace: bool = True) -> dict[str, Any]:
    """Store one merchant's stock at the current system. ``replace`` drops an earlier log of the same merchant here."""
    sys_addr = UniverseAddress(address.galaxy, address.x, address.y, address.z, address.system, 0)
    with contextlib.closing(connect()) as con, con:
        replaced = 0
        if replace:
            replaced = con.execute("DELETE FROM visits WHERE packed = ? AND merchant = ?", (sys_addr.packed(), merchant)).rowcount
        cur = con.execute(
            "INSERT INTO visits (seen_at, packed, portal, galaxy, station, merchant, economy, note) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), sys_addr.packed(), sys_addr.portal(), sys_addr.galaxy, station, merchant, economy, note),
        )
        vid = cur.lastrowid
        con.executemany(
            "INSERT INTO items (visit_id, name, item_class, category, price, currency, quantity, detail) VALUES (?,?,?,?,?,?,?,?)",
            [(vid, i["name"], i.get("item_class"), i.get("category"), i.get("price"), i.get("currency"), i.get("quantity"), i.get("detail"))
             for i in items],
        )
    return {"visit_id": vid, "items": len(items), "replaced_previous": bool(replaced), "portal": sys_addr.portal(), "merchant": merchant}


def find_items(here: UniverseAddress, query: str | None = None, item_class: str | None = None, max_price: float | None = None,
               currency: str | None = None, merchant: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    sql = ("SELECT i.*, v.portal, v.packed, v.station, v.merchant, v.economy, v.seen_at FROM items i JOIN visits v ON v.id = i.visit_id "
           "WHERE v.galaxy = ?")
    args: list[Any] = [here.galaxy]
    if query:
        sql += " AND (lower(i.name) LIKE ? OR lower(coalesce(i.category,'')) LIKE ?)"
        args += [f"%{query.lower()}%", f"%{query.lower()}%"]
    if item_class:
        sql += " AND upper(coalesce(i.item_class,'')) = ?"
        args.append(item_class.upper())
    if max_price is not None:
        sql += " AND i.price IS NOT NULL AND i.price <= ?"
        args.append(max_price)
    if currency:
        sql += " AND lower(coalesce(i.currency,'')) = ?"
        args.append(currency.lower())
    if merchant:
        sql += " AND lower(v.merchant) LIKE ?"
        args.append(f"%{merchant.lower()}%")
    if not db_path().is_file():
        return []
    with contextlib.closing(connect()) as con:
        rows = [dict(r) for r in con.execute(sql, args)]
    for r in rows:
        a = UniverseAddress.from_packed(r["packed"])
        r["distance_ly"] = round(here.distance_ly(a))
        r["seen_hours_ago"] = round((time.time() - r["seen_at"]) / 3600, 1)
    rows.sort(key=lambda r: (r["distance_ly"], r["price"] if r["price"] is not None else 1e18))
    return rows[:limit]


def shops_at(address: UniverseAddress) -> list[dict[str, Any]]:
    if not db_path().is_file():
        return []
    sys_addr = UniverseAddress(address.galaxy, address.x, address.y, address.z, address.system, 0)
    with contextlib.closing(connect()) as con:
        visits = [dict(v) for v in con.execute("SELECT * FROM visits WHERE packed = ? ORDER BY seen_at DESC", (sys_addr.packed(),))]
        for v in visits:
            v["items"] = [dict(i) for i in con.execute("SELECT name, item_class, category, price, currency, quantity, detail FROM items WHERE visit_id = ?", (v["id"],))]
            v["seen_hours_ago"] = round((time.time() - v["seen_at"]) / 3600, 1)
    return visits


def summary() -> dict[str, Any]:
    if not db_path().is_file():
        return {"systems": 0, "visits": 0, "items": 0}
    with contextlib.closing(connect()) as con:
        return {
            "systems": con.execute("SELECT COUNT(DISTINCT packed) FROM visits").fetchone()[0],
            "visits": con.execute("SELECT COUNT(*) FROM visits").fetchone()[0],
            "items": con.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        }
