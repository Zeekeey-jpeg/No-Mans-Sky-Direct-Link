"""Synthetic save fixture. No real player data is used anywhere in the test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nms_direct_link.save.decompress import compress_save
from nms_direct_link.save.mapping import load_mapping

NOW = 1_790_000_000


def _inv(slots, cls="B", width=8, height=6, valid=20, stats=None):
    return {
        "Slots": slots,
        "ValidSlotIndices": [{"X": i % width, "Y": i // width} for i in range(valid)],
        "Class": {"InventoryClass": cls},
        "BaseStatValues": stats or [],
        "Width": width,
        "Height": height,
    }


def _slot(item_id, kind, amount=1, max_amount=1, x=0, y=0, damage=0.0, installed=True):
    return {
        "Type": {"InventoryType": kind},
        "Id": item_id,
        "Amount": amount,
        "MaxAmount": max_amount,
        "DamageFactor": damage,
        "FullyInstalled": installed,
        "Index": {"X": x, "Y": y},
    }


def readable_save() -> dict:
    return {
        "Version": 4745,
        "Platform": "Win|Final",
        "ActiveContext": "Main",
        "CommonStateData": {
            "SaveName": "Test",
            "TotalPlayTime": 7200,
            "UsedDiscoveryOwnersV2": [{"LID": "", "UID": "owner-1", "USN": "tester", "PTK": "ST"}],
        },
        "BaseContext": {
            "GameMode": 1,
            "PlayerStateData": {
                "Units": 1_000_000,
                "Nanites": 250,
                "Specials": 40,
                "Health": 8,
                "Shield": 100,
                "ShipHealth": 8,
                "HasAccessToNexus": True,
                "KnownPortalRunes": 5,
                "UniverseAddress": {"RealityIndex": 0, "GalacticAddress": {"VoxelX": 100, "VoxelY": -3, "VoxelZ": -500, "SolarSystemIndex": 427, "PlanetIndex": 1}},
                "PreviousUniverseAddress": {"RealityIndex": 0, "GalacticAddress": {"VoxelX": 101, "VoxelY": -3, "VoxelZ": -500, "SolarSystemIndex": 12, "PlanetIndex": 0}},
                "FreighterUniverseAddress": {"RealityIndex": 0, "GalacticAddress": {"VoxelX": 100, "VoxelY": -3, "VoxelZ": -500, "SolarSystemIndex": 427, "PlanetIndex": 0}},
                "CurrentMissionID": "^TEST_MISSION",
                "CurrentMissionSeed": 0,
                "DifficultyState": {"Preset": {"DifficultyPresetType": "Normal"}, "Settings": {"CurrencyCost": {"CurrencyCostDifficulty": "Normal"}, "TutorialEnabled": True}},
                "Inventory": _inv([_slot("^OXYGEN", "Substance", 300, 9999, 0, 0), _slot("^LAND1", "Substance", 1200, 9999, 1, 0), _slot("^NANOTUBES", "Product", 3, 5, 2, 0)], cls="C", valid=24),
                "Inventory_TechOnly": _inv([_slot("^JET1", "Technology"), _slot("^UP_JET4#12345", "Technology", x=1), _slot("^UP_HAZ2#99", "Technology", x=2, damage=0.5), _slot("^PROTECT", "Technology", x=3)], valid=14),
                "Inventory_Cargo": _inv([_slot("^LAND1", "Substance", 500, 9999)], valid=10),
                "ShipOwnership": [
                    {
                        "Name": "Test Hauler",
                        "Resource": {"Filename": "MODELS/COMMON/SPACECRAFT/DROPSHIPS/DROPSHIP_PROC.SCENE.MBIN", "Seed": [True, "0xABC"]},
                        "Inventory": _inv([_slot("^UP_HYPX#777", "Technology"), _slot("^SHIPCHARGE", "Product", 2, 5, x=1)], cls="A", valid=30, stats=[{"BaseStatID": "^SHIP_DAMAGE", "Value": 20.0}]),
                        "Inventory_TechOnly": _inv([_slot("^HYPERDRIVE", "Technology"), _slot("^UP_HYP4#4242", "Technology", x=1), _slot("^SHIPSHIELD", "Technology", x=2)], cls="A", valid=12),
                        "Inventory_Cargo": _inv([], cls="A", valid=0),
                    },
                    {"Name": "", "Resource": {"Filename": "", "Seed": [False, "0x0"]}, "Inventory": _inv([], valid=0), "Inventory_TechOnly": _inv([], valid=0), "Inventory_Cargo": _inv([], valid=0)},
                ],
                "PrimaryShip": 0,
                "Multitools": [{"Name": "", "IsLarge": False, "Store": _inv([_slot("^LASER", "Technology"), _slot("^UP_LASER3#55", "Technology", x=1)], cls="B", valid=10, stats=[{"BaseStatID": "^WEAPON_MINING", "Value": 1.5}])}],
                "ActiveMultioolIndex": 0,
                "FreighterInventory": _inv([_slot("^STELLAR2", "Substance", 2500, 9999)], cls="C", valid=40),
                "FreighterInventory_TechOnly": _inv([_slot("^F_HYPERDRIVE", "Technology")], cls="C", valid=8),
                "VehicleOwnership": [],
                "Chest1Inventory": _inv([_slot("^ASTEROID2", "Substance", 800, 9999)], valid=50),
                "FleetFrigates": [
                    {"CustomName": "Sunrise", "InventoryClass": {"InventoryClass": "A"}, "FrigateClass": {"FrigateClass": "Trade"}, "Race": {"AlienRace": "Traders"},
                     "TotalNumberOfExpeditions": 3, "TotalNumberOfSuccessfulEvents": 10, "TotalNumberOfFailedEvents": 1, "NumberOfTimesDamaged": 0, "TraitIDs": ["^TRADE_PRI", "^"], "Stats": [1, 2, 3]},
                ],
                "FleetExpeditions": [
                    {"StartTime": NOW - 3600, "PauseTime": 0, "ExpeditionDuration": 7200, "ExpeditionCategory": {"ExpeditionCategory": "Trade"}, "Events": [{}, {}],
                     "AllFrigateIndices": [0], "ActiveFrigateIndices": [0], "DamagedFrigateIndices": [], "DestroyedFrigateIndices": []},
                ],
                "SettlementStatesV2": [
                    {"Name": "", "UniverseAddress": 0, "Population": 0, "PendingJudgementType": {"SettlementJudgementType": "None"}, "BuildingStates": [0, 0]},
                    {"Name": "Testville", "UniverseAddress": "0x11AB00FDE0C064", "Population": 12, "PendingJudgementType": {"SettlementJudgementType": "Dispute"},
                     "LastJudgementTime": NOW - 86400, "BuildingStates": [0, 3, 0], "Stats": [5, 6, 7], "Perks": []},
                ],
                "MissionProgress": [{"Mission": "^DONE", "Progress": -1, "Seed": 0, "Data": 0}, {"Mission": "^ACTIVE", "Progress": 2, "Seed": 9, "Data": 0}],
                "MissionRecurrences": [{"MissionID": "^DM_QS_REWARDS", "RecurrenceDeadline": NOW + 3600}],
                "KnownTech": ["^JET1", "^HYPERDRIVE"],
                "KnownProducts": ["^NANOTUBES"],
                "KnownRefinerRecipes": ["^REFINERECIPE_1"],
                "PersistentPlayerBases": [
                    {"Name": "Home", "GalacticAddress": "0x11AB00FDE0C064", "BaseType": {"PersistentBaseTypes": "HomePlanetBase"}, "Objects": [{}, {}, {}], "LastUpdateTimestamp": NOW - 100},
                    {"Name": "Default", "GalacticAddress": 0, "BaseType": {"PersistentBaseTypes": "UITempShipBase"}, "Objects": []},
                ],
                "TeleportEndpoints": [
                    {"Name": "Home", "TeleporterType": "Base", "IsFavourite": True, "UniverseAddress": {"RealityIndex": 0, "GalacticAddress": {"VoxelX": 100, "VoxelY": -3, "VoxelZ": -500, "SolarSystemIndex": 427, "PlanetIndex": 1}}},
                ],
            },
        },
        "DiscoveryManagerData": {
            "DiscoveryData-v1": {
                "ReserveStore": 0,
                "ReserveManaged": 0,
                "Store": {
                    "Record": [
                        {"DD": {"UA": 0x11AB00FDE0C064, "DT": "Planet"}, "FL": {"C": 1, "U": 0}, "OWS": {"UID": "owner-1", "TS": NOW}},
                        {"DD": {"UA": 0x11AB00FDE0C064, "DT": "Animal"}, "FL": {"C": 1, "U": 0}, "OWS": {"UID": "owner-1", "TS": NOW}},
                        {"DD": {"UA": 0x11AB00FDE0C064, "DT": "Animal"}, "FL": {"C": 1, "U": 1}, "OWS": {"UID": "owner-1", "TS": NOW}},
                        {"DD": {"UA": 0x11AB00FDE0C064, "DT": "Flora"}, "FL": {"C": 1, "U": 1}, "OWS": {"UID": "someone-else", "TS": NOW}},
                        {"DD": {"UA": "0x11AB00FDE0C064", "DT": "Mineral"}, "FL": {"C": 1, "U": 0}, "OWS": {"UID": "owner-1", "TS": NOW}},
                    ]
                },
                "Available": [],
                "Enqueued": [],
            }
        },
    }


@pytest.fixture(scope="session")
def mapping():
    return load_mapping()


@pytest.fixture
def readable():
    return readable_save()


@pytest.fixture
def save_dir(tmp_path: Path, mapping, readable) -> Path:
    """A fake HelloGames/NMS/st_<id>/ folder with two compressed, obfuscated saves."""
    acct = tmp_path / "st_000000000000000"
    acct.mkdir()
    obf = mapping.obfuscate(readable)
    payload = json.dumps(obf, separators=(",", ":")).encode("utf-8") + b"\x00"
    (acct / "save.hg").write_bytes(compress_save(payload))
    older = dict(readable)
    older["BaseContext"] = json.loads(json.dumps(readable["BaseContext"]))
    older["BaseContext"]["PlayerStateData"]["Nanites"] = 1
    (acct / "save2.hg").write_bytes(compress_save(json.dumps(mapping.obfuscate(older)).encode("utf-8") + b"\x00"))
    import os
    import time

    old = time.time() - 3600
    os.utime(acct / "save2.hg", (old, old))
    (acct / "mf_save.hg").write_bytes(b"\x00" * 432)
    return acct


@pytest.fixture
def env_save_dir(monkeypatch, save_dir: Path) -> Path:
    monkeypatch.setenv("NMS_SAVE_DIR", str(save_dir))
    monkeypatch.delenv("NMS_SAVE_FILE", raising=False)
    monkeypatch.delenv("NMS_SAVE_SLOT", raising=False)
    return save_dir
