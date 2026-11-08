"""Curated gameplay knowledge: nanite methods, upgrade classes, portal glyphs, explainers.

Everything here is static text with a source and a date. Rates are community estimates, not game
constants; they are labelled as such in every response. Re-check after each named update.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KNOWLEDGE_CHECKED = "2026-11-08 (game 7.13 Forsaken)"


@dataclass(frozen=True)
class NaniteMethod:
    key: str
    name: str
    rate_per_hour: tuple[int, int]  # community estimate, low/high
    requires: str
    how: str
    needs_units: int = 0
    needs_nexus: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


NANITE_METHODS: list[NaniteMethod] = [
    NaniteMethod(
        "runaway_mould", "Runaway Mould farm (Curious Deposits)", (15000, 40000),
        "A planet with Curious Deposits, a base with 3-4 refiners",
        "Harvest Curious Deposits for Runaway Mould, refine 5 Mould -> 1 Nanite Cluster. Deposits respawn once you move ~600u away. "
        "Alt recipes: 1 Atlantideum + 1 Pugneum -> 3 Mould; 1 Living Slime -> 1 Mould.",
        tags=("farm", "best"),
    ),
    NaniteMethod(
        "ship_scrap", "Scrap starships, sell the upgrade modules", (10000, 30000),
        "A large units bankroll (tens of millions) and a station with ship traffic",
        "Buy ships, scrap them at the station Starship Outfitting terminal, sell the S/A-class modules to the technology merchant. "
        "Selling twice in one system crashes the price (up to ~80%), so rotate systems.",
        needs_units=20_000_000, tags=("units_to_nanites",),
    ),
    NaniteMethod(
        "suspicious_packets", "Suspicious Packets from the outlaw-station contraband dealer", (4000, 25000),
        "~74k units per packet, access to an outlaw (pirate) system",
        "Buy Suspicious Packets (Technology), open them, sell the upgrade modules to a technology merchant. Modules sell for ~300-1100 nanites by class.",
        needs_units=2_000_000, tags=("units_to_nanites", "pirate_system"),
    ),
    NaniteMethod(
        "upload_discoveries", "Upload your pending discoveries", (0, 0),
        "Nothing: open Discoveries and upload",
        "Every un-uploaded planet, system, creature, plant and mineral pays nanites when uploaded. Planet and system entries pay the most; "
        "completing a full fauna roster on a planet pays a bonus (community figures: hundreds to a few thousand per planet).",
        tags=("free", "instant"),
    ),
    NaniteMethod(
        "sentinels", "Sentinel / Corrupted Sentinel hunting", (2000, 5000),
        "A combat-ready multitool and ship",
        "Fight sentinels for Pugneum (refines to nanites), Hyaline Brains, and Tainted Metal at corrupted sites (refine to nanites).",
        tags=("combat",),
    ),
    NaniteMethod(
        "derelict_freighter", "Derelict freighters", (2500, 3500),
        "An Emergency Signal Scanner (price climbs with same-day purchases)",
        "Run the derelict for Tainted Metal, salvaged modules and the captain's log rewards; sell modules to the merchant.",
        tags=("combat", "units_bonus"),
    ),
    NaniteMethod(
        "larval_cores", "Larval Cores from Whispering Eggs", (1000, 2000),
        "An abandoned building, a fast jetpack",
        "Break Whispering Eggs, grab the Larval Core (~50 nanites each when sold or refined), fly before the Biological Horrors catch you.",
        tags=("early_game",),
    ),
    NaniteMethod(
        "nexus_missions", "Nexus missions (Space Anomaly)", (300, 1200),
        "Anomaly access",
        "Pick missions that pay nanites (150-400 each); daily and weekend missions also pay Quicksilver.",
        needs_nexus=True, tags=("anomaly",),
    ),
    NaniteMethod(
        "xeno_arena", "Xeno Arena creature battles (added 6.3, April 2026)", (0, 0),
        "Tamed companions",
        "Winning arena battles pays nanites. Rates are not yet established by the community.",
        tags=("new",),
    ),
]

UPGRADE_CLASSES = {
    "C": "C-class: lowest tier, 1-2 stats, cheapest (~65 nanites at a merchant, estimate).",
    "B": "B-class: 2-3 stats (~150 nanites, estimate).",
    "A": "A-class: 3-4 stats (~300 nanites, estimate).",
    "S": "S-class: 3-4 stats at the top of their ranges (~500 nanites, estimate). Max three installed per upgrade family per inventory.",
    "X": "X-class: illegal/outlaw modules with wider stat ranges (can roll above or below S). Sold by outlaw-station dealers and found in buried caches.",
}

EXPLAINERS: dict[str, str] = {
    "nanites": "Nanites (Nanite Clusters) buy blueprints, upgrade modules at station technology merchants, starship/multitool class upgrades and some expedition items. "
               "Fastest sources: a Runaway Mould farm, scrapping ships, Suspicious Packets, uploading discoveries, and selling salvaged modules.",
    "upgrade modules": "Procedural upgrade modules come in C/B/A/S (and outlaw X) classes. Install up to three per family per inventory; "
                       "place them adjacent to the core technology for an adjacency bonus, and in supercharged slots for a large multiplier. "
                       "Stats are rolled from the module's seed when installed; the save stores only the ID and seed.",
    "hyperdrive": "The stock hyperdrive reaches ~100 ly. Hyperdrive upgrade modules add range by class (S-class the most; three max). "
                  "Coloured stars need the Cadmium (red), Emeril (green), Indium (blue) and Atlantid (purple) drives, sold by Iteration: Hyperion on the Anomaly; "
                  "they do not count toward the module limit. Each warp uses fuel; a Warp Cell restores 25%.",
    "portal glyphs": "A portal address is 12 glyphs: planet (1), system index (3), Y (2), Z (3), X (3), each glyph a hex digit 0-F. "
                     "Glyphs are learned from Travellers' graves (16 total). Use nms_convert_coordinates to translate any form.",
    "economy": "Each system has an economy type (e.g. Mining, Technology, Trading) and a wealth tier (T1 low, T2 medium, T3 high: Wealthy/Affluent/Advanced/Booming/Flourishing/Opulent/Prosperous/High Supply). "
               "Higher tiers have more and better trade goods; the community reports more S-class modules at T3 stations (anecdotal). Pirate (outlaw) systems sell X-class modules and contraband.",
    "frigates": "Frigates join your freighter's fleet and run expeditions (combat, trade, exploration, industrial, support). "
                "Expeditions take real hours; damaged frigates must be repaired before they can be sent again. Debrief at the fleet command room.",
    "settlements": "A settlement is a planetary town you oversee: build structures, settle disputes (judgements), manage debt and happiness. "
                   "Overseer decisions unlock buildings and production. Check pending judgements regularly.",
    "discoveries": "Scanning plants, minerals, creatures, planets and systems creates discovery records. Uploading them in the Discoveries menu pays nanites; "
                   "records not yet uploaded are your nanite backlog.",
    "quicksilver": "Quicksilver is earned from Nexus daily/weekend missions and community research, and spent at the Anomaly Quicksilver Synthesis Companion on cosmetics and some items.",
    "save file": "NMS writes save*.hg on manual save points, when you exit your ship, and on a periodic autosave. This server reads that file only; "
                 "your live state can lag by seconds to minutes, longest while you stay in the ship.",
}


def explain(topic: str) -> str | None:
    t = topic.strip().lower()
    if t in EXPLAINERS:
        return EXPLAINERS[t]
    for k, v in EXPLAINERS.items():
        if t in k or k in t:
            return v
    if t in ("c", "b", "a", "s", "x") or t.endswith("-class") or t.endswith(" class"):
        cls = t[0].upper()
        if cls in UPGRADE_CLASSES:
            return UPGRADE_CLASSES[cls]
    return None


def topics() -> list[str]:
    return sorted(EXPLAINERS) + [f"{c}-class" for c in UPGRADE_CLASSES]
