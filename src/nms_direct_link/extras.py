"""Everything else the save records: lifetime stats, standing and language, trade log, wonders,
companions, hangar, waypoints and a single "what's ready" timer dashboard.

All read-only views over :class:`SaveSnapshot`. Category and race names come from libMBIN enums
(``GcAlienRace``, ``GcWonder*Category``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .save.address import UniverseAddress
from .save.model import SaveSnapshot, humanise_id

RACES = ["Gek", "Vy'keen", "Korvax", "Sentinel", "Atlas", "Diplomats", "Exotics", "None", "Autophage"]

WONDER_CATEGORIES = {
    "WonderCreatureRecords": ("creature", ["Largest herbivore", "Smallest herbivore", "Largest carnivore", "Smallest carnivore",
                                           "Most intelligent", "Most vicious", "Hot-world creature", "Cold-world creature",
                                           "Toxic-world creature", "Radioactive-world creature", "Exotic creature",
                                           "Aquatic creature", "Robotic creature", "Flying creature", "Cave creature"]),
    "WonderPlanetRecords": ("planet", ["Hottest planet", "Coldest planet", "Most toxic planet", "Most radioactive planet",
                                       "Most anomalous planet", "Largest planet", "Smallest planet", "Highest altitude reached",
                                       "Lowest altitude reached", "Most perfect planet", "Least perfect planet"]),
    "WonderFloraRecords": ("flora", ["Flora fact 1", "Flora fact 2", "Flora fact 3", "Flora fact 4",
                                     "Cold-world flora", "Hot-world flora", "Radioactive-world flora", "Toxic-world flora"]),
    "WonderMineralRecords": ("mineral", ["Mineral fact 1", "Mineral fact 2", "Mineral fact 3", "Metal mineral",
                                         "Cold-world mineral", "Hot-world mineral", "Radioactive-world mineral", "Toxic-world mineral"]),
    "WonderTreasureRecords": ("treasure", ["Loot", "Document", "Bio-sample", "Fossil", "Plant", "Tool", "Farm", "Sea loot",
                                           "Sea horror", "Salvage", "Bones", "Space horror", "Space bones"]),
}

STAT_LABELS = {
    "DIST_WARP": "Warps made", "ALIENS_MET": "Aliens met", "DEATHS": "Deaths", "UPGRADE_COUNT": "Upgrades installed",
    "TIMES_IN_SPACE": "Times launched into space", "RARE_SCANNED": "Rare items scanned", "DISC_CRE_LAND": "Land creatures discovered",
    "DISC_CRE_WATER": "Aquatic creatures discovered", "DISC_CRE_AGGRO": "Aggressive creatures discovered",
    "DISC_ALL_CREATU": "Planets with all creatures discovered", "BIG_SCAN_MIN": "Units earned from scanning",
    "APP_SESSIONS": "Play sessions", "EX_HOT_WALK": "Distance walked on hot worlds (u)", "EX_COLD_WALK": "Distance walked on cold worlds (u)",
    "TSEEN_SYSTEMS": "Systems seen", "BLACKHOLE_WARPS": "Black hole warps", "PETS_ADOPTED": "Companions adopted",
    "QUEENS_KILLED": "Biological horror queens killed", "SPIDERS_KILLED": "Spiders killed", "GRUBS_KILLED": "Grubs killed",
    "STATIONS_OWNED": "Space stations directed", "DISC_P_DEAD": "Dead planets discovered", "TRA_MET": "Gek met",
    "WAR_MET": "Vy'keen met", "EXP_MET": "Korvax met", "ROAD_KILL": "Creatures run over", "PHOTO_DEAD": "Photos of dead planets",
    "ATLAS_LOOPS": "Atlas path loops", "MEDITATION": "Times meditated", "COMM_CREA_FED": "Creatures fed",
    "UPGRADE_TIME": "Time spent upgrading (s)", "SENTINEL_KILLS": "Sentinels destroyed", "PIRATES_KILLED": "Pirates destroyed",
    "DIST_WALKED": "Distance walked (u)", "DIST_FLOWN": "Distance flown (u)", "PLANTS_PLANTED": "Plants planted",
    "DEPOTS_BROKEN": "Depots raided", "FRIGATES_PURCH": "Frigates purchased", "SHIPS_BOUGHT": "Ships bought",
    "MONEY": "Units earned", "NANITES": "Nanites earned", "WORDS_LEARNT": "Words learned",
}

STANDING_LABELS = {
    "TRA_STANDING": "Gek", "WAR_STANDING": "Vy'keen", "EXP_STANDING": "Korvax", "BUI_STANDING": "Autophage", "NEXUS_STAND": "Space Anomaly (Nexus)",
    "TGUILD_STAND": "Merchants' Guild", "WGUILD_STAND": "Mercenaries' Guild", "EGUILD_STAND": "Explorers' Guild",
    "PIRATE_STAND": "Outlaws",
}


def _stat_value(v: Any) -> int | float | None:
    if isinstance(v, dict):
        if "IntValue" in v:
            return v["IntValue"]
        if "FloatValue" in v:
            return round(float(v["FloatValue"]), 2)
        return None
    return v if isinstance(v, (int, float)) else None


def _iso(ts: int | None) -> str | None:
    if not ts or ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _addr(v: Any) -> UniverseAddress | None:
    try:
        return UniverseAddress.from_packed(v) if v not in (0, "0x0", None, "") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------- stats / standing


def player_stats(snap: SaveSnapshot) -> dict[str, Any]:
    out: dict[str, dict[str, Any]] = {}
    for g in snap.player.get("Stats") or []:
        gid = str(g.get("GroupId", "")).lstrip("^")
        if gid not in ("GLOBAL_STATS", "TELEMETRY_STATS"):
            continue
        for e in g.get("Stats") or []:
            sid = str(e.get("Id", "")).lstrip("^")
            val = _stat_value(e.get("Value"))
            if val in (None, 0, -1) or sid.endswith("STANDING") or sid.endswith("_STAND"):
                continue
            out[sid] = {"label": STAT_LABELS.get(sid, sid.replace("_", " ").title()), "value": val}
    return {"play_time_hours": round(snap.play_time_seconds / 3600, 1), "stats": out}


def standing(snap: SaveSnapshot) -> dict[str, Any]:
    stand: dict[str, Any] = {}
    for g in snap.player.get("Stats") or []:
        if str(g.get("GroupId", "")).lstrip("^") != "GLOBAL_STATS":
            continue
        for e in g.get("Stats") or []:
            sid = str(e.get("Id", "")).lstrip("^")
            if sid in STANDING_LABELS:
                stand[STANDING_LABELS[sid]] = _stat_value(e.get("Value")) or 0
    for label in STANDING_LABELS.values():
        stand.setdefault(label, 0)
    words: dict[str, int] = dict.fromkeys(RACES[:3] + ["Atlas", "Autophage"], 0)
    for wg in snap.player.get("KnownWordGroups") or []:
        for i, known in enumerate(wg.get("Races") or []):
            if known and i < len(RACES) and RACES[i] in words:
                words[RACES[i]] += 1
    return {"standing": stand, "words_known": words, "word_groups_total": len(snap.player.get("KnownWordGroups") or []),
            "note": "Standing values are the game's internal reputation counters; higher is better. Station tech merchants discount by standing (since Orbital 4.6)."}


# ---------------------------------------------------------------------------- trade log


def trade_log(snap: SaveSnapshot) -> dict[str, Any]:
    played = snap.play_time_seconds
    here = snap.address
    systems: dict[int, dict[str, Any]] = {}
    for t in snap.player.get("TradingSupplyData") or []:
        a = _addr(t.get("GalacticAddress"))
        if a is None:
            continue
        a = UniverseAddress(a.galaxy, a.x, a.y, a.z, a.system, 0)  # markets are per system, not per planet
        key = a.packed()
        entry = systems.setdefault(key, {"address": a, "products": []})
        ts = int(t.get("Timestamp", 0) or 0)
        supply = float(t.get("Supply", 0.0) or 0.0)
        demand = float(t.get("Demand", 0.0) or 0.0)
        entry["products"].append({
            "id": t.get("Product"), "name": humanise_id(str(t.get("Product", ""))), "is_product": bool(t.get("IsProduct")),
            "supply": round(supply, 4), "demand": round(demand, 2),
            "saturated": demand < 0, "hours_ago_played": round(max(played - ts, 0) / 3600, 1) if ts else None,
        })
    out = []
    for e in systems.values():
        a: UniverseAddress = e["address"]
        out.append({"portal": a.portal(), "system": f"system {a.system:03X} @ {a.booster()}", "distance_ly": round(here.distance_ly(a)),
                    "products_traded": len(e["products"]), "saturated": [p["name"] for p in e["products"] if p["saturated"]],
                    "products": e["products"]})
    out.sort(key=lambda d: d["distance_ly"])
    return {"systems": out, "note": "The game keeps the last ~100 trades. Negative demand means you sold there and pushed the price down; it recovers over time."}


# ---------------------------------------------------------------------------- wonders


def wonder_records(snap: SaveSnapshot) -> dict[str, Any]:
    out: dict[str, list[dict[str, Any]]] = {}
    for key, (kind, labels) in WONDER_CATEGORIES.items():
        rows = []
        for i, r in enumerate(snap.player.get(key) or []):
            gen = r.get("GenerationID") or []
            val = float(r.get("WonderStatValue", 0.0) or 0.0)
            a = _addr(gen[0]) if gen else None
            if a is None and not val:
                continue
            rows.append({"record": labels[i] if i < len(labels) else f"{kind} record {i + 1}", "value": round(val, 2),
                         "where": a.portal() if a else None, "planet_index": a.planet if a else None,
                         "distance_ly": round(snap.address.distance_ly(a)) if a else None})
        if rows:
            out[kind] = rows
    return {"records": out, "note": "Wonder records are the extremes you have scanned, as shown in the Catalogue's Wonders page."}


# ---------------------------------------------------------------------------- companions / hangar


def companions(snap: SaveSnapshot) -> dict[str, Any]:
    p = snap.player
    pets = []
    for i, pet in enumerate(p.get("Pets") or []):
        cid = pet.get("CreatureID")
        if not cid or cid == "^":
            continue
        name = pet.get("CustomSpeciesName")
        a = _addr(pet.get("UA"))
        pets.append({"slot": i + 1, "name": None if name in (None, "^") else name, "species": humanise_id(str(cid)),
                     "biome": (pet.get("Biome") or {}).get("Biome"), "predator": bool(pet.get("Predator")),
                     "scale": round(float(pet.get("Scale", 1.0) or 1.0), 2), "has_fur": bool(pet.get("HasFur")),
                     "adopted": _iso(pet.get("BirthTime")), "home": a.portal() if a else None,
                     "traits": pet.get("Traits"), "mood": pet.get("MoodValues")})
    eggs = [e for e in p.get("Eggs") or [] if e.get("CreatureID") not in (None, "^")]
    team = [m.get("PetIndex") for m in ((p.get("PetBattleTeam") or {}).get("TeamMembers") or []) if m.get("PetIndex", -1) >= 0]
    slots = p.get("UnlockedPetSlots") or []
    return {"companions": pets, "eggs": len(eggs), "battle_team_slots": [i + 1 for i in team],
            "unlocked_slots": sum(1 for s in slots if s), "max_slots": len(slots),
            "battle_victories": p.get("PetBattlerVictories")}


def hangar(snap: SaveSnapshot) -> dict[str, Any]:
    p = snap.player
    ships = snap.ships()
    corvettes = [s for s in ships if s["archetype"] == "Corvette"]
    corvette_storage = [i for i in snap.inventories() if i.owner == "corvette storage"]
    pilots = [sp for sp in p.get("SquadronPilots") or [] if (sp.get("NPCResource") or {}).get("Filename")]
    workers = [w for w in p.get("NPCWorkers") or [] if w.get("HiredWorker")]
    fleet = [f for f in p.get("FreighterFleet") or [] if (f.get("Resource") or {}).get("Filename")]
    return {
        "ships": ships, "ship_slots_used": len(ships), "ship_slots": len(p.get("ShipOwnership") or []),
        "corvettes": corvettes, "corvette_storage_items": sum(len(i.slots) for i in corvette_storage),
        "corvette_draft_in_progress": bool(p.get("CorvetteDraftShipSeed")),
        "multitools": snap.multitools(), "multitool_slots": len(p.get("Multitools") or []),
        "squadron_pilots": [{"rank": sp.get("PilotRank"), "ship": (sp.get("ShipResource") or {}).get("Filename", "").split("/")[-1]} for sp in pilots],
        "squadron_slots_unlocked": sum(1 for s in p.get("SquadronUnlockedPilotSlots") or [] if s),
        "hired_workers": len(workers), "frigates": len(p.get("FleetFrigates") or []), "fleet_capital_ships": len(fleet),
    }


# ---------------------------------------------------------------------------- waypoints


def waypoints(snap: SaveSnapshot) -> dict[str, Any]:
    p = snap.player
    here = snap.address
    out_wp = []
    for w in p.get("GalaxyWaypoints") or []:
        ga = w.get("Address") or {}
        a = UniverseAddress.from_save({"RealityIndex": w.get("RealityIndex", 0), "GalacticAddress": ga})
        out_wp.append({"type": (w.get("Type") or {}).get("GalaxyWaypointType"), "event": w.get("EventId"),
                       "portal": a.portal(), "distance_ly": round(here.distance_ly(a))})
    markers = []
    for m in p.get("MarkerStack") or []:
        a = _addr(m.get("GalacticAddress"))
        markers.append({"mission": m.get("MissionID"), "event": m.get("Event"),
                        "building": (m.get("BuildingClass") or {}).get("BuildingClass"),
                        "portal": a.portal() if a else None, "planet_index": a.planet if a else None,
                        "distance_ly": round(here.distance_ly(a)) if a else None})
    grave = None
    gua = p.get("GraveUniverseAddress")
    graves = [i for i in snap.inventories() if i.owner == "grave"]
    if graves and graves[0].slots and isinstance(gua, dict):
        a = UniverseAddress.from_save(gua)
        grave = {"portal": a.portal(), "planet_index": a.planet, "in_space": bool(p.get("SpaceGrave")),
                 "items": [f"{s.amount} {s.name}" for s in graves[0].slots], "distance_ly": round(here.distance_ly(a))}
    nexus = p.get("NexusUniverseAddress")
    nexus_a = UniverseAddress.from_save(nexus) if isinstance(nexus, dict) else None
    visited = []
    seen = set()
    for v in p.get("VisitedSystems") or []:
        a = _addr(v)
        if a and a.system_key() not in seen:
            seen.add(a.system_key())
            visited.append(a)
    return {"galaxy_waypoints": out_wp, "mission_markers": markers, "grave": grave,
            "space_anomaly": nexus_a.portal() if nexus_a and nexus_a.system else None,
            "recently_visited_systems": [{"portal": a.portal(), "distance_ly": round(here.distance_ly(a))} for a in visited[:30]],
            "visited_systems_count": len(visited)}


# ---------------------------------------------------------------------------- timers


def timers(snap: SaveSnapshot, now: int | None = None) -> dict[str, Any]:
    now = now or int(datetime.now(tz=UTC).timestamp())
    items: list[dict[str, Any]] = []
    for e in snap.fleet_expeditions(now=now):
        items.append({"what": f"Frigate expedition ({e['category']})", "ready": e["complete"], "at": e["eta"],
                      "seconds_left": e["seconds_remaining"], "action": "Debrief at your freighter's fleet command room"})
    rec = snap.recurring_missions()
    reset = [r for r in rec if r["deadline_epoch"] <= now]
    if reset:
        items.append({"what": f"{len(reset)} daily/weekly mission set(s) have refreshed", "ready": True, "at": None, "seconds_left": 0,
                      "action": "New missions at the Nexus and mission boards", "missions": [r["id"] for r in reset]})
    for r in rec:
        left = r["deadline_epoch"] - now
        if left > 0:
            items.append({"what": f"Mission reset `{r['id']}`", "ready": False, "at": r["deadline"], "seconds_left": left,
                          "action": "New missions become available"})
    for s in snap.settlements():
        if s["pending_judgement"] and s["pending_judgement"] != "None":
            items.append({"what": f"Settlement '{s['name']}' judgement ({s['pending_judgement']})", "ready": True, "at": None,
                          "seconds_left": 0, "action": "Visit the settlement and make the overseer decision"})
    graves = [i for i in snap.inventories() if i.owner == "grave" and i.slots]
    if graves:
        items.append({"what": "Item grave waiting", "ready": True, "at": None, "seconds_left": 0,
                      "action": "Recover your dropped inventory (see nms_get_waypoints)"})
    if snap.discovery_backlog()["pending_upload"]:
        items.append({"what": f"{snap.discovery_backlog()['pending_upload']} discoveries waiting to upload", "ready": True, "at": None,
                      "seconds_left": 0, "action": "Upload in the Discoveries menu for nanites"})
    items.sort(key=lambda d: (not d["ready"], d["seconds_left"]))
    return {"now": _iso(now), "items": items, "ready_now": sum(1 for i in items if i["ready"])}
