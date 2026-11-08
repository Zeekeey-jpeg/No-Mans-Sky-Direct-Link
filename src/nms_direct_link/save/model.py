"""Typed, tolerant view over a de-obfuscated No Man's Sky save.

Every accessor returns plain Python data and degrades gracefully when a key is missing, because
the save gains keys with each game update. Field names follow the MBINCompiler mapping
(``Units``, ``Nanites``, ``Specials`` = quicksilver, ``Inventory_TechOnly`` …).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .address import UniverseAddress
from .decompress import decompress_save
from .mapping import KeyMapping, is_obfuscated, load_mapping

_PROC_RE = re.compile(r"^\^?(?P<family>[A-Z0-9_]+?)(?P<tier>[1-4X])?#(?P<seed>\d+)$")
_TIER_TO_CLASS = {"1": "C", "2": "B", "3": "A", "4": "S", "X": "X"}

PRESET_NAMES = {0: "Unspecified", 1: "Normal", 2: "Creative", 3: "Survival", 4: "Ambient", 5: "Permadeath", 6: "Seasonal"}

MODULE_FAMILIES = {
    # exosuit
    "UP_ENGY": ("Life Support", "exosuit"), "UP_HAZ": ("Hazard Protection", "exosuit"),
    "UP_JET": ("Movement System (jetpack)", "exosuit"), "UP_SHLD": ("Defence Systems (shield)", "exosuit"),
    "UP_UNW": ("Aeration Membrane (underwater)", "exosuit"), "UP_RAD": ("Radiation Deflector", "exosuit"),
    "UP_TOX": ("Toxin Suppressor", "exosuit"), "UP_COLD": ("Thermic Layer (cold)", "exosuit"),
    "UP_HOT": ("Coolant Network (heat)", "exosuit"), "UP_SNSUIT": ("Sentinel exosuit module", "exosuit"),
    # multitool
    "UP_LASER": ("Mining Beam", "multitool"), "UP_SCAN": ("Scanner", "multitool"),
    "UP_BOLT": ("Boltcaster", "multitool"), "UP_GREN": ("Plasma Launcher", "multitool"),
    "UP_TGREN": ("Geology Cannon", "multitool"), "UP_RAIL": ("Blaze Javelin", "multitool"),
    "UP_SHOT": ("Scatter Blaster", "multitool"), "UP_SMG": ("Pulse Spitter", "multitool"),
    "UP_CANN": ("Neutron Cannon", "multitool"), "UP_SENGUN": ("Sentinel weapon module", "multitool"),
    # starship
    "UP_PULSE": ("Pulse Engine", "starship"), "UP_LAUN": ("Launch Thruster", "starship"),
    "UP_HYP": ("Hyperdrive", "starship"), "UP_S_SHL": ("Deflector Shield", "starship"),
    "UP_SGUN": ("Photon Cannon", "starship"), "UP_SLASR": ("Phase Beam", "starship"),
    "UP_SSHOT": ("Positron Ejector", "starship"), "UP_SMINI": ("Infra-Knife Accelerator", "starship"),
    "UP_SBLOB": ("Cyclotron Ballista", "starship"), "UP_SROCK": ("Rocket Launcher", "starship"),
    "UP_SENT": ("Sentinel starship module", "starship"), "UP_LIVING": ("Living ship module", "starship"),
    # freighter / exocraft
    "UP_FRHYP": ("Freighter Hyperdrive", "freighter"), "UP_FRSHIELD": ("Freighter Shield", "freighter"),
    "UP_EXGUN": ("Exocraft Mounted Cannon", "exocraft"), "UP_EXLAS": ("Exocraft Mining Laser", "exocraft"),
    "UP_EXENG": ("Exocraft Engine", "exocraft"), "UP_BOOST": ("Exocraft Boost", "exocraft"),
    "UP_MCGUN": ("Minotaur Cannon", "exocraft"), "UP_MCLAS": ("Minotaur Laser", "exocraft"),
    "UP_MCENG": ("Minotaur Engine", "exocraft"),
}

# Compact display names for common IDs. Partial by design; unknown IDs fall back to a humanised ID.
ITEM_NAMES = {
    "JET1": "Jetpack", "ENERGY": "Life Support", "PROTECT": "Hazard Protection", "LAUNCHER": "Launch Thruster",
    "SHIPSHIELD": "Deflector Shield", "SHIPGUN1": "Photon Cannon", "SHIPJUMP1": "Pulse Engine",
    "SHIPROCKETS": "Rocket Launcher", "HYPERDRIVE": "Hyperdrive", "LASER": "Mining Beam", "SCAN1": "Scanner",
    "SCANBINOC1": "Analysis Visor", "TERRAINEDITOR": "Terrain Manipulator", "BOLT": "Boltcaster",
    "F_HYPERDRIVE": "Freighter Hyperdrive", "UT_ENERGY": "Life support (unit)", "GROUND_SHIELD": "Exocraft shield",
    "VEHICLE_ENGINE": "Exocraft Engine", "VEHICLE_BOOST": "Exocraft Boost", "MECH_ENGINE": "Minotaur Engine",
    "OXYGEN": "Oxygen", "FUEL1": "Carbon", "FUEL2": "Condensed Carbon", "LAND1": "Ferrite Dust",
    "LAND2": "Pure Ferrite", "LAND3": "Magnetised Ferrite", "CATALYST1": "Sodium", "CATALYST2": "Sodium Nitrate",
    "LAUNCHSUB": "Di-hydrogen", "LAUNCHSUB2": "Deuterium", "ASTEROID1": "Silver", "ASTEROID2": "Gold",
    "ASTEROID3": "Platinum", "CAVE1": "Cobalt", "CAVE2": "Ionised Cobalt", "WATER1": "Salt", "WATER2": "Chlorine",
    "YELLOW2": "Copper", "RED2": "Cadmium", "GREEN2": "Emeril", "BLUE2": "Indium", "STELLAR2": "Chromatic Metal",
    "LUSH1": "Paraffinium", "TOXIC1": "Ammonia", "RADIO1": "Uranium", "COLD1": "Dioxite", "HOT1": "Phosphorus",
    "DUSTY1": "Pyrite", "NANOTUBES": "Carbon Nanotubes", "SHIPCHARGE": "Starship Launch Fuel",
    "SENTINEL_LOOT": "Sentinel loot", "SCRAP_TECH": "Salvaged tech scrap", "NANITES": "Nanite Cluster",
}

STAT_NAMES = {"^WEAPON_DAMAGE": "damage", "^WEAPON_MINING": "mining", "^WEAPON_SCAN": "scan",
              "^SHIP_DAMAGE": "damage", "^SHIP_SHIELD": "shield", "^SHIP_AGILE": "manoeuvrability",
              "^SHIP_HYPERDRIVE": "hyperdrive"}


def humanise_id(item_id: str) -> str:
    raw = item_id.lstrip("^")
    base = raw.split("#", 1)[0]
    if base in ITEM_NAMES:
        return ITEM_NAMES[base]
    m = _PROC_RE.match(item_id)
    if m:
        fam = m.group("family")
        name = MODULE_FAMILIES.get(fam, (fam.replace("UP_", "").title() + " upgrade", ""))[0]
        return f"{name} upgrade"
    return base.replace("_", " ").title()


@dataclass(frozen=True)
class Slot:
    id: str
    name: str
    kind: str  # Technology | Product | Substance
    amount: int
    max_amount: int
    damage: float
    installed: bool
    x: int
    y: int

    @property
    def is_upgrade_module(self) -> bool:
        return bool(_PROC_RE.match(self.id))

    @property
    def module_class(self) -> str | None:
        m = _PROC_RE.match(self.id)
        if not m:
            return None
        return _TIER_TO_CLASS.get(m.group("tier") or "", None)

    @property
    def module_family(self) -> str | None:
        m = _PROC_RE.match(self.id)
        return m.group("family") if m else None

    @property
    def module_seed(self) -> int | None:
        m = _PROC_RE.match(self.id)
        return int(m.group("seed")) if m else None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id, "name": self.name, "type": self.kind, "amount": self.amount,
            "max_amount": self.max_amount, "damage": self.damage, "installed": self.installed,
            "slot": {"x": self.x, "y": self.y},
        }
        if self.is_upgrade_module:
            fam = self.module_family or ""
            d.update({
                "upgrade": True, "class": self.module_class, "family": fam,
                "upgrades": MODULE_FAMILIES.get(fam, ("?", "?"))[0], "seed": self.module_seed,
            })
        return d


@dataclass(frozen=True)
class Inventory:
    owner: str  # e.g. "exosuit", "exosuit tech", "ship 1", "multitool 1", "freighter", "storage 3"
    slots: list[Slot]
    inventory_class: str | None
    width: int
    height: int
    base_stats: dict[str, float]
    valid_slots: int

    @property
    def technology(self) -> list[Slot]:
        return [s for s in self.slots if s.kind == "Technology"]

    @property
    def items(self) -> list[Slot]:
        return [s for s in self.slots if s.kind != "Technology"]

    @property
    def upgrade_modules(self) -> list[Slot]:
        return [s for s in self.slots if s.is_upgrade_module]

    @property
    def damaged(self) -> list[Slot]:
        return [s for s in self.slots if s.kind == "Technology" and (s.damage > 0 or not s.installed)]

    @property
    def free_slots(self) -> int:
        return max(self.valid_slots - len(self.slots), 0)

    def to_dict(self, include_slots: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "owner": self.owner, "class": self.inventory_class, "size": f"{self.width}x{self.height}",
            "valid_slots": self.valid_slots, "used_slots": len(self.slots), "free_slots": self.free_slots,
            "base_stats": self.base_stats,
        }
        if include_slots:
            d["slots"] = [s.to_dict() for s in self.slots]
        return d


def _parse_inventory(owner: str, inv: Any) -> Inventory | None:
    if not isinstance(inv, dict):
        return None
    slots: list[Slot] = []
    for s in inv.get("Slots", []) or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("Id", ""))
        idx = s.get("Index") or {}
        kind = (s.get("Type") or {}).get("InventoryType", "Unknown")
        slots.append(
            Slot(
                id=sid, name=humanise_id(sid), kind=kind, amount=int(s.get("Amount", 0) or 0),
                max_amount=int(s.get("MaxAmount", 0) or 0), damage=float(s.get("DamageFactor", 0.0) or 0.0),
                installed=bool(s.get("FullyInstalled", True)), x=int(idx.get("X", 0) or 0), y=int(idx.get("Y", 0) or 0),
            )
        )
    stats = {}
    for st in inv.get("BaseStatValues", []) or []:
        if isinstance(st, dict) and "BaseStatID" in st:
            stats[STAT_NAMES.get(st["BaseStatID"], str(st["BaseStatID"]).lstrip("^").lower())] = float(st.get("Value", 0.0) or 0.0)
    return Inventory(
        owner=owner, slots=slots, inventory_class=(inv.get("Class") or {}).get("InventoryClass"),
        width=int(inv.get("Width", 0) or 0), height=int(inv.get("Height", 0) or 0), base_stats=stats,
        valid_slots=len(inv.get("ValidSlotIndices", []) or []),
    )


@dataclass(frozen=True)
class Discovery:
    kind: str
    address: UniverseAddress
    uploaded: bool
    owner: str
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "address": self.address.to_dict(), "uploaded": self.uploaded, "timestamp": self.timestamp}


class SaveSnapshot:
    """One parsed save. Build with :func:`load_snapshot`."""

    def __init__(self, data: dict[str, Any], *, path: Path | None = None, mapping: KeyMapping | None = None,
                 unknown_keys: set[str] | None = None, modified: datetime | None = None) -> None:
        self.data = data
        self.path = path
        self.mapping = mapping
        self.unknown_keys = unknown_keys or set()
        self.modified = modified

    # ---- raw access ---------------------------------------------------
    @property
    def context(self) -> dict[str, Any]:
        active = self.data.get("ActiveContext", "Main")
        key = "ExpeditionContext" if active == "Season" else "BaseContext"
        ctx = self.data.get(key)
        if not isinstance(ctx, dict):
            ctx = self.data.get("BaseContext") or {}
        return ctx

    @property
    def player(self) -> dict[str, Any]:
        return self.context.get("PlayerStateData") or {}

    @property
    def common(self) -> dict[str, Any]:
        return self.data.get("CommonStateData") or {}

    # ---- summary ------------------------------------------------------
    @property
    def version(self) -> int:
        return int(self.data.get("Version", 0) or 0)

    @property
    def platform(self) -> str:
        return str(self.data.get("Platform", ""))

    @property
    def active_context(self) -> str:
        return str(self.data.get("ActiveContext", "Main"))

    @property
    def game_mode(self) -> str:
        preset = ((self.player.get("DifficultyState") or {}).get("Preset") or {}).get("DifficultyPresetType")
        if preset:
            return str(preset)
        return PRESET_NAMES.get(int(self.context.get("GameMode", 0) or 0), "Unknown")

    @property
    def difficulty(self) -> dict[str, str]:
        settings = (self.player.get("DifficultyState") or {}).get("Settings") or {}
        out: dict[str, str] = {}
        for k, v in settings.items():
            if isinstance(v, dict) and len(v) == 1:
                out[k] = str(next(iter(v.values())))
            elif isinstance(v, (bool, int, float, str)):
                out[k] = str(v)
        return out

    @property
    def units(self) -> int:
        return int(self.player.get("Units", 0) or 0)

    @property
    def nanites(self) -> int:
        return int(self.player.get("Nanites", 0) or 0)

    @property
    def quicksilver(self) -> int:
        return int(self.player.get("Specials", 0) or 0)

    @property
    def play_time_seconds(self) -> int:
        return int(self.common.get("TotalPlayTime", 0) or 0)

    @property
    def save_name(self) -> str:
        return str(self.common.get("SaveName", "") or "")

    @property
    def health(self) -> dict[str, Any]:
        p = self.player
        return {"health": p.get("Health"), "shield": p.get("Shield"), "energy": p.get("Energy"),
                "ship_health": p.get("ShipHealth"), "hazard": p.get("Hazard")}

    @property
    def has_nexus_access(self) -> bool:
        return bool(self.player.get("HasAccessToNexus", False))

    @property
    def known_glyphs(self) -> int:
        return int(self.player.get("KnownPortalRunes", 0) or 0)

    # ---- location -----------------------------------------------------
    @property
    def address(self) -> UniverseAddress:
        return UniverseAddress.from_save(self.player.get("UniverseAddress") or {})

    @property
    def previous_address(self) -> UniverseAddress | None:
        p = self.player.get("PreviousUniverseAddress")
        return UniverseAddress.from_save(p) if isinstance(p, dict) else None

    @property
    def freighter_address(self) -> UniverseAddress | None:
        p = self.player.get("FreighterUniverseAddress")
        return UniverseAddress.from_save(p) if isinstance(p, dict) else None

    # ---- inventories --------------------------------------------------
    def inventories(self) -> list[Inventory]:
        p = self.player
        out: list[Inventory] = []
        for label, key in (("exosuit", "Inventory"), ("exosuit tech", "Inventory_TechOnly"), ("exosuit cargo", "Inventory_Cargo")):
            inv = _parse_inventory(label, p.get(key))
            if inv:
                out.append(inv)
        for i, ship in enumerate(p.get("ShipOwnership") or [], start=1):
            if not isinstance(ship, dict) or not (ship.get("Inventory") or {}).get("Slots") and not (ship.get("Inventory_TechOnly") or {}).get("Slots"):
                continue
            name = ship.get("Name") or f"ship {i}"
            for label, key in ((f"{name} (ship {i})", "Inventory"), (f"{name} (ship {i}) tech", "Inventory_TechOnly"), (f"{name} (ship {i}) cargo", "Inventory_Cargo")):
                inv = _parse_inventory(label, ship.get(key))
                if inv and (inv.slots or inv.valid_slots):
                    out.append(inv)
        for i, mt in enumerate(p.get("Multitools") or [], start=1):
            if not isinstance(mt, dict):
                continue
            name = mt.get("Name") or f"multitool {i}"
            inv = _parse_inventory(f"{name} (multitool {i})", mt.get("Store"))
            if inv and (inv.slots or inv.valid_slots):
                out.append(inv)
        for label, key in (("freighter", "FreighterInventory"), ("freighter tech", "FreighterInventory_TechOnly"), ("freighter cargo", "FreighterInventory_Cargo")):
            inv = _parse_inventory(label, p.get(key))
            if inv and (inv.slots or inv.valid_slots):
                out.append(inv)
        for i, veh in enumerate(p.get("VehicleOwnership") or [], start=1):
            if not isinstance(veh, dict):
                continue
            for label, key in ((f"exocraft {i}", "Inventory"), (f"exocraft {i} tech", "Inventory_TechOnly"), (f"exocraft {i} cargo", "Inventory_Cargo")):
                inv = _parse_inventory(label, veh.get(key))
                if inv and inv.slots:
                    out.append(inv)
        for n in range(1, 11):
            inv = _parse_inventory(f"storage {n}", p.get(f"Chest{n}Inventory"))
            if inv and inv.slots:
                out.append(inv)
        for label, key in (("storage magic", "ChestMagicInventory"), ("storage magic 2", "ChestMagic2Inventory"),
                           ("cooking", "CookingIngredientsInventory"), ("corvette storage", "CorvetteStorageInventory"),
                           ("rocket locker", "RocketLockerInventory"), ("grave", "GraveInventory")):
            inv = _parse_inventory(label, p.get(key))
            if inv and inv.slots:
                out.append(inv)
        return out

    def find_items(self, query: str) -> list[tuple[Inventory, Slot]]:
        q = query.strip().lower().lstrip("^")
        hits: list[tuple[Inventory, Slot]] = []
        for inv in self.inventories():
            for s in inv.slots:
                if q in s.id.lower() or q in s.name.lower():
                    hits.append((inv, s))
        return hits

    # ---- ships / multitools summary -----------------------------------
    def ships(self) -> list[dict[str, Any]]:
        out = []
        primary = self.player.get("PrimaryShip")
        for i, ship in enumerate(self.player.get("ShipOwnership") or []):
            if not isinstance(ship, dict):
                continue
            inv = _parse_inventory("ship", ship.get("Inventory"))
            tech = _parse_inventory("ship tech", ship.get("Inventory_TechOnly"))
            if not inv or (not inv.slots and not inv.valid_slots):
                continue
            res = ship.get("Resource") or {}
            filename = str(res.get("Filename", ""))
            out.append({
                "index": i, "name": ship.get("Name") or f"ship {i + 1}", "primary": primary == i,
                "class": inv.inventory_class, "archetype": _ship_type(filename), "seed": (res.get("Seed") or [None, None])[1],
                "base_stats": inv.base_stats, "general_slots": inv.valid_slots,
                "tech_slots": tech.valid_slots if tech else 0,
                "tech": [s.name for s in (inv.technology + (tech.technology if tech else []))],
                "upgrades": [f"{s.module_class}-class {s.name}" for s in (inv.upgrade_modules + (tech.upgrade_modules if tech else []))],
            })
        return out

    def multitools(self) -> list[dict[str, Any]]:
        out = []
        active = self.player.get("ActiveMultioolIndex", self.player.get("ActiveMultitoolIndex"))
        for i, mt in enumerate(self.player.get("Multitools") or []):
            if not isinstance(mt, dict):
                continue
            store = _parse_inventory("multitool", mt.get("Store"))
            if not store:
                continue
            out.append({
                "index": i, "name": mt.get("Name") or f"multitool {i + 1}", "active": active == i,
                "class": store.inventory_class, "slots": store.valid_slots, "large": bool(mt.get("IsLarge", False)),
                "base_stats": store.base_stats, "tech": [s.name for s in store.technology],
                "upgrades": [f"{s.module_class}-class {s.name}" for s in store.upgrade_modules],
            })
        return out

    # ---- discoveries --------------------------------------------------
    def discoveries(self) -> list[Discovery]:
        dm = self.data.get("DiscoveryManagerData") or {}
        dd = dm.get("DiscoveryData-v1") or {}
        store = dd.get("Store") or {}
        out: list[Discovery] = []
        for r in store.get("Record", []) or []:
            if not isinstance(r, dict):
                continue
            d = r.get("DD") or {}
            fl = r.get("FL") or {}
            ows = r.get("OWS") or {}
            try:
                addr = UniverseAddress.from_packed(d.get("UA", 0))
            except (TypeError, ValueError):
                continue
            out.append(Discovery(kind=str(d.get("DT", "Unknown")), address=addr, uploaded=int(fl.get("U", 0) or 0) > 0,
                                 owner=str(ows.get("UID", "")), timestamp=int(ows.get("TS", 0) or 0)))
        return out

    def own_discovery_owner_ids(self) -> set[str]:
        """Owner UIDs that belong to this save (from CommonStateData.UsedDiscoveryOwnersV2)."""
        ids: set[str] = set()
        for o in self.common.get("UsedDiscoveryOwnersV2") or []:
            if isinstance(o, dict):
                uid = o.get("UID")
                if uid:
                    ids.add(str(uid))
        return ids

    def discovery_backlog(self) -> dict[str, Any]:
        recs = self.discoveries()
        own = self.own_discovery_owner_ids()
        mine = [r for r in recs if (r.owner in own)] if own else recs
        pending = [r for r in mine if not r.uploaded]
        by_type: dict[str, int] = {}
        for r in pending:
            by_type[r.kind] = by_type.get(r.kind, 0) + 1
        systems: dict[tuple, int] = {}
        for r in pending:
            systems[r.address.system_key()] = systems.get(r.address.system_key(), 0) + 1
        return {
            "total_records": len(recs), "own_records": len(mine), "own_uploaded": len(mine) - len(pending),
            "pending_upload": len(pending), "pending_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "pending_systems": len(systems),
        }

    # ---- bases / teleporters ------------------------------------------
    def bases(self) -> list[dict[str, Any]]:
        out = []
        for b in self.player.get("PersistentPlayerBases") or []:
            if not isinstance(b, dict):
                continue
            btype = (b.get("BaseType") or {}).get("PersistentBaseTypes", "")
            if btype in ("UITempShipBase", "ExternalPlanetBase", "PlayerShipBase"):
                continue
            try:
                addr = UniverseAddress.from_packed(b.get("GalacticAddress", 0))
            except (TypeError, ValueError):
                addr = None
            out.append({
                "name": b.get("Name") or "(unnamed)", "type": btype, "objects": len(b.get("Objects") or []),
                "address": addr.to_dict() if addr else None,
                "last_updated": _iso(b.get("LastUpdateTimestamp")),
            })
        return out

    def teleporters(self) -> list[dict[str, Any]]:
        out = []
        for t in self.player.get("TeleportEndpoints") or []:
            if not isinstance(t, dict):
                continue
            ua = t.get("UniverseAddress")
            out.append({
                "name": t.get("Name") or "(unnamed)", "type": t.get("TeleporterType"),
                "favourite": bool(t.get("IsFavourite", False)),
                "address": UniverseAddress.from_save(ua).to_dict() if isinstance(ua, dict) else None,
            })
        return out

    # ---- missions -----------------------------------------------------
    def current_mission(self) -> dict[str, Any]:
        return {"id": self.player.get("CurrentMissionID"), "seed": self.player.get("CurrentMissionSeed"),
                "previous_id": self.player.get("PreviousMissionID")}

    def missions_in_progress(self) -> list[dict[str, Any]]:
        out = []
        for m in self.player.get("MissionProgress") or []:
            if isinstance(m, dict) and int(m.get("Progress", -1) or -1) > 0:
                out.append({"id": m.get("Mission"), "stage": m.get("Progress"), "seed": m.get("Seed"), "data": m.get("Data")})
        return out

    def recurring_missions(self) -> list[dict[str, Any]]:
        out = []
        for r in self.player.get("MissionRecurrences") or []:
            if isinstance(r, dict):
                dl = int(r.get("RecurrenceDeadline", 0) or 0)
                out.append({"id": r.get("MissionID"), "deadline": _iso(dl), "deadline_epoch": dl})
        out.sort(key=lambda d: d["deadline_epoch"])
        return out

    # ---- fleet --------------------------------------------------------
    def frigates(self) -> list[dict[str, Any]]:
        out = []
        for f in self.player.get("FleetFrigates") or []:
            if not isinstance(f, dict):
                continue
            out.append({
                "name": f.get("CustomName") or "(unnamed)",
                "class": (f.get("InventoryClass") or {}).get("InventoryClass"),
                "role": (f.get("FrigateClass") or {}).get("FrigateClass"),
                "race": (f.get("Race") or {}).get("AlienRace"),
                "expeditions": f.get("TotalNumberOfExpeditions"), "successes": f.get("TotalNumberOfSuccessfulEvents"),
                "failures": f.get("TotalNumberOfFailedEvents"), "times_damaged": f.get("NumberOfTimesDamaged"),
                "traits": [t for t in (f.get("TraitIDs") or []) if t and t != "^"], "stats": f.get("Stats"),
            })
        return out

    def fleet_expeditions(self, now: int | None = None) -> list[dict[str, Any]]:
        now = now or int(datetime.now(tz=UTC).timestamp())
        out = []
        for e in self.player.get("FleetExpeditions") or []:
            if not isinstance(e, dict):
                continue
            start = int(e.get("StartTime", 0) or 0)
            duration = int(e.get("ExpeditionDuration", 0) or 0)
            pause = int(e.get("PauseTime", 0) or 0)
            eta = start + duration + (pause if pause > 0 else 0)  # pause handling is a best guess
            out.append({
                "category": (e.get("ExpeditionCategory") or {}).get("ExpeditionCategory") if isinstance(e.get("ExpeditionCategory"), dict) else e.get("ExpeditionCategory"),
                "started": _iso(start), "duration_hours": round(duration / 3600, 1), "eta": _iso(eta),
                "seconds_remaining": max(eta - now, 0), "complete": eta <= now,
                "frigates": len(e.get("AllFrigateIndices") or []), "damaged": len(e.get("DamagedFrigateIndices") or []),
                "destroyed": len(e.get("DestroyedFrigateIndices") or []), "events": len(e.get("Events") or []),
            })
        return out

    # ---- settlements --------------------------------------------------
    def settlements(self) -> list[dict[str, Any]]:
        out = []
        for s in self.player.get("SettlementStatesV2") or []:
            if not isinstance(s, dict) or not s.get("Name"):
                continue
            ua = s.get("UniverseAddress", 0)
            try:
                addr = UniverseAddress.from_packed(ua).to_dict() if ua else None
            except (TypeError, ValueError):
                addr = None
            out.append({
                "name": s.get("Name"), "address": addr, "population": s.get("Population"),
                "pending_judgement": (s.get("PendingJudgementType") or {}).get("SettlementJudgementType"),
                "last_judgement": _iso(s.get("LastJudgementTime")), "stats": s.get("Stats"), "perks": s.get("Perks"),
                "buildings_in_progress": sum(1 for b in (s.get("BuildingStates") or []) if isinstance(b, int) and b > 0),
            })
        return out

    # ---- knowledge ----------------------------------------------------
    def known(self) -> dict[str, Any]:
        p = self.player
        return {
            "technology": [humanise_id(t) for t in p.get("KnownTech") or []],
            "technology_ids": list(p.get("KnownTech") or []),
            "products": len(p.get("KnownProducts") or []),
            "refiner_recipes": len(p.get("KnownRefinerRecipes") or []),
            "words": len(p.get("KnownWords") or []),
            "glyphs": self.known_glyphs,
        }

    # ---- export -------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        return {
            "save": {"path": str(self.path) if self.path else None, "modified": self.modified.isoformat() if self.modified else None,
                     "version": self.version, "platform": self.platform, "active_context": self.active_context,
                     "mapping": self.mapping.version if self.mapping else None, "unknown_keys": len(self.unknown_keys)},
            "mode": self.game_mode, "play_time_hours": round(self.play_time_seconds / 3600, 1),
            "currencies": {"units": self.units, "nanites": self.nanites, "quicksilver": self.quicksilver},
            "location": self.address.to_dict(), "health": self.health, "nexus_access": self.has_nexus_access,
            "current_mission": self.current_mission(),
        }


def _ship_type(filename: str) -> str:
    f = filename.upper()
    for key, name in (("FIGHTER", "Fighter"), ("SHUTTLE", "Shuttle"), ("DROPSHIP", "Hauler"), ("SCIENTIFIC", "Explorer"),
                      ("ROYAL", "Exotic"), ("BIOPART", "Living Ship"), ("SENTINEL", "Sentinel Interceptor"),
                      ("SAILSHIP", "Solar Ship"), ("CORVETTE", "Corvette"), ("FREIGHTER", "Freighter")):
        if key in f:
            return name
    return "Unknown"


def _iso(ts: Any) -> str | None:
    try:
        t = int(ts or 0)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return datetime.fromtimestamp(t, tz=UTC).isoformat()


def load_snapshot(path: str | Path, mapping: KeyMapping | None = None) -> SaveSnapshot:
    """Read, decompress, de-obfuscate and wrap one save file. Never writes."""
    p = Path(path)
    raw = p.read_bytes()
    text = decompress_save(raw).decode("utf-8", errors="replace")
    data = json.loads(text)
    unknown: set[str] = set()
    if isinstance(data, dict) and is_obfuscated(data):
        mapping = mapping or load_mapping()
        data = mapping.deobfuscate(data, unknown)
    st = p.stat()
    return SaveSnapshot(data, path=p, mapping=mapping, unknown_keys=unknown,
                        modified=datetime.fromtimestamp(st.st_mtime, tz=UTC))
