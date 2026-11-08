"""Upgrade planning, station briefs and price memory.

Combines three sources: what the save says you have installed, what you have scanned in shops,
and rough merchant prices by class. Prices are community estimates unless you have scanned a shop.
"""

from __future__ import annotations

from typing import Any

from . import shops
from .save.address import UniverseAddress
from .save.model import MODULE_FAMILIES, SaveSnapshot

CLASS_RANK = {"C": 1, "B": 2, "A": 3, "S": 4, "X": 4}
EST_NANITES = {"C": 65, "B": 150, "A": 300, "S": 500}  # community estimates for station tech merchants
MAX_PER_FAMILY = 3

# core technology id -> (upgrade family, inventory group, priority 1 = most useful)
CORE_TO_FAMILY = {
    "^HYPERDRIVE": ("UP_HYP", "starship", 1), "^SHIPJUMP1": ("UP_PULSE", "starship", 3), "^LAUNCHER": ("UP_LAUN", "starship", 4),
    "^SHIPSHIELD": ("UP_S_SHL", "starship", 2), "^SHIPGUN1": ("UP_SGUN", "starship", 3), "^SHIPLAS1": ("UP_SLASR", "starship", 3),
    "^JET1": ("UP_JET", "exosuit", 2), "^ENERGY": ("UP_ENGY", "exosuit", 3), "^PROTECT": ("UP_HAZ", "exosuit", 3),
    "^SHIELD": ("UP_SHLD", "exosuit", 4),
    "^LASER": ("UP_LASER", "multitool", 2), "^SCAN1": ("UP_SCAN", "multitool", 1), "^BOLT": ("UP_BOLT", "multitool", 4),
    "^F_HYPERDRIVE": ("UP_FRHYP", "freighter", 2),
}

STATION_MERCHANTS = [
    ("technology merchant", "Upgrade modules for suit, ship and multitool (nanites); blueprints"),
    ("starship outfitter", "Starship upgrades, cargo slot expansions"),
    ("exosuit merchant", "Exosuit slot expansions (drop pod alternative)"),
    ("multi-tool merchant", "Multitools for sale (and their upgrades)"),
    ("galactic trade terminal", "Buy/sell goods; best place to dump trade items"),
    ("scrap dealer", "Ship scrap and salvaged modules (outlaw stations)"),
    ("mission board", "Guild missions for standing, units and nanites"),
]


def _owner_group(owner: str) -> str:
    o = owner.lower()
    if o.startswith("exosuit"):
        return "exosuit"
    if "(ship" in o:
        return "starship"
    if "multitool" in o:
        return "multitool"
    if o.startswith("freighter"):
        return "freighter"
    return "other"


def upgrade_gaps(snap: SaveSnapshot) -> list[dict[str, Any]]:
    """For each upgradeable core technology you own: how many modules of which class are installed, and the gap."""
    gaps: dict[tuple[str, str], dict[str, Any]] = {}
    installed: dict[tuple[str, str], list[str]] = {}
    ships = snap.ships()
    ship_idx = next((s["index"] for s in ships if s["primary"]), ships[0]["index"] if ships else 0)
    ship_token = f"(ship {ship_idx + 1})"
    tools = snap.multitools()
    tool_idx = next((m["index"] for m in tools if m["active"]), 0)
    tool_token = f"(multitool {tool_idx + 1})"
    for inv in snap.inventories():
        group = _owner_group(inv.owner)
        if group == "starship" and ship_token not in inv.owner:
            continue  # plan for the ship you fly
        if group == "multitool" and tool_token not in inv.owner:
            continue  # and the multitool in your hand
        for s in inv.technology:
            if s.id in CORE_TO_FAMILY:
                fam, grp, prio = CORE_TO_FAMILY[s.id]
                gaps.setdefault((grp, fam), {"group": grp, "family": fam, "upgrades": MODULE_FAMILIES.get(fam, (fam,))[0],
                                             "priority": prio, "core": s.name})
            if s.is_upgrade_module and s.module_family:
                fam = s.module_family.rstrip("X") if s.module_family not in MODULE_FAMILIES else s.module_family
                installed.setdefault((group, fam), []).append(s.module_class or "?")
    out = []
    for key, g in gaps.items():
        classes = sorted(installed.get(key, []), key=lambda c: -CLASS_RANK.get(c, 0))
        free = max(MAX_PER_FAMILY - len(classes), 0)
        weakest = min(classes, key=lambda c: CLASS_RANK.get(c, 0)) if classes else None
        want = []
        if free:
            want.append(f"{free} free slot{'s' if free > 1 else ''}")
        lows = [c for c in classes if CLASS_RANK.get(c, 0) < CLASS_RANK["S"]]
        if lows:
            want.append("replace " + ", ".join(lows) + " with S")
        out.append({**g, "installed": classes, "free_slots": free, "weakest": weakest, "to_do": want,
                    "complete": not free and all(c in ("S", "X") for c in classes)})
    out.sort(key=lambda d: (d["complete"], d["priority"], -d["free_slots"]))
    return out


def upgrade_plan(snap: SaveSnapshot, budget_nanites: int | None = None) -> dict[str, Any]:
    nanites = snap.nanites if budget_nanites is None else budget_nanites
    here = snap.address
    gaps = upgrade_gaps(snap)
    steps = []
    spend = 0
    for g in gaps:
        if g["complete"]:
            continue
        name = g["upgrades"].split(" (")[0]
        seen = [r for r in shops.find_items(here, query=name, limit=500) if _same_family(r, name, g["group"])]
        floor = 0 if g["free_slots"] else CLASS_RANK.get(g["weakest"] or "", 0)
        useful = [r for r in seen if CLASS_RANK.get((r.get("item_class") or "").upper(), 0) > floor]
        useful.sort(key=lambda r: (-CLASS_RANK.get((r.get("item_class") or "").upper(), 0), r["distance_ly"], r["price"] if r.get("price") is not None else 1e18))
        best = useful[0] if useful else None
        est = EST_NANITES["S"]
        if best and best.get("price") is not None and (best.get("currency") or "").lower().startswith("nanite"):
            est = int(best["price"])
        needed = g["free_slots"] + sum(1 for c in g["installed"] if CLASS_RANK.get(c, 0) < CLASS_RANK["S"])
        buyable = 0
        for _ in range(needed):
            if spend + est > nanites:
                break
            spend += est
            buyable += 1
        affordable = buyable > 0
        steps.append({
            "group": g["group"], "upgrade": g["upgrades"], "installed": g["installed"], "free_slots": g["free_slots"],
            "action": ", ".join(g["to_do"]) if g["to_do"] else "none",
            "best_seen": {k: best[k] for k in ("name", "item_class", "price", "currency", "portal", "merchant", "distance_ly")} if best else None,
            "estimated_nanites": est, "modules_needed": needed, "estimated_total": est * needed,
            "affordable_now": affordable, "affordable_count": buyable,
        })
    return {"nanites": snap.nanites, "budget": nanites, "planned_spend": spend, "steps": steps,
            "complete_families": [g["upgrades"] for g in gaps if g["complete"]],
            "note": "Up to three upgrade modules per technology type per inventory. Prices are community estimates unless a scanned shop listed one."}


_OTHER_GROUP_WORDS = {"freighter": ("freighter",), "exocraft": ("exocraft", "minotaur", "nautilon", "colossus", "roamer", "nomad", "pilgrim")}


def _same_family(row: dict[str, Any], name: str, group: str) -> bool:
    """Shop item belongs to this upgrade family (e.g. 'Hyperdrive' for the starship, not the freighter's)."""
    text = f"{row.get('name', '')} {row.get('category') or ''}".lower()
    if name.lower() not in text:
        return False
    for grp, words in _OTHER_GROUP_WORDS.items():
        if grp != group and any(w in text for w in words):
            return False
    return True


def station_brief(snap: SaveSnapshot) -> dict[str, Any]:
    here = snap.address
    scanned = shops.shops_at(here)
    scanned_names = {v["merchant"] for v in scanned}
    plan = upgrade_plan(snap)
    from .extras import trade_log

    sys_key = UniverseAddress(here.galaxy, here.x, here.y, here.z, here.system, 0).portal()
    trade_here = next((s for s in trade_log(snap)["systems"] if s["portal"] == sys_key), None)
    look_for = [s for s in plan["steps"] if s["free_slots"] or s["action"] != "none"][:5]
    merchants = []
    for m, what in STATION_MERCHANTS:
        merchants.append({"merchant": m, "sells": what, "scanned_here": m in scanned_names})
    first = "technology merchant" if look_for else "galactic trade terminal"
    return {
        "system": sys_key, "save_written": snap.modified.isoformat() if snap.modified else None,
        "wallet": {"units": snap.units, "nanites": snap.nanites, "quicksilver": snap.quicksilver},
        "scanned_shops_here": scanned, "merchants": merchants, "open_first": first,
        "look_for": look_for, "trade_here": trade_here,
        "note": "Merchant stock is not in the save. Open the merchant and ask 'what's in this shop?' to scan it.",
    }


def best_prices(here: UniverseAddress, query: str | None = None, item_class: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    rows = shops.find_items(here, query=query, item_class=item_class, limit=10_000)
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    count: dict[tuple[str, str, str], int] = {}
    for r in rows:
        if r.get("price") is None:
            continue
        key = (r["name"].strip().lower(), (r.get("item_class") or "").upper(), (r.get("currency") or "").lower())
        count[key] = count.get(key, 0) + 1
        if key not in best or r["price"] < best[key]["price"]:
            best[key] = r
    out = []
    for key, r in best.items():
        prices = [x["price"] for x in rows if x.get("price") is not None and (x["name"].strip().lower(), (x.get("item_class") or "").upper(), (x.get("currency") or "").lower()) == key]
        out.append({"name": r["name"], "item_class": r.get("item_class"), "currency": r.get("currency"), "cheapest": r["price"],
                    "highest": max(prices), "times_seen": count[key], "where": r["portal"], "merchant": r["merchant"],
                    "station": r.get("station"), "distance_ly": r["distance_ly"]})
    out.sort(key=lambda d: (d["name"].lower(), d["cheapest"]))
    return out[:limit]
