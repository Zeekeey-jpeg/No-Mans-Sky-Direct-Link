from __future__ import annotations

import json

import pytest

from nms_direct_link.save import UniverseAddress, list_saves, load_snapshot, newest_save
from nms_direct_link.save.decompress import MAGIC, SaveFormatError, compress_save, decompress_save
from nms_direct_link.save.mapping import is_obfuscated


def test_roundtrip_compression():
    data = json.dumps({"hello": "world" * 1000}).encode()
    blob = compress_save(data)
    assert int.from_bytes(blob[:4], "little") == MAGIC
    assert decompress_save(blob) == data


def test_plain_json_passthrough():
    assert decompress_save(b'{"a":1}\x00\x00') == b'{"a":1}'


def test_bad_magic_rejected():
    with pytest.raises(SaveFormatError):
        decompress_save(b"\x00" * 32)


def test_mapping_roundtrip(mapping, readable):
    obf = mapping.obfuscate(readable)
    assert is_obfuscated(obf)
    assert "F2P" in obf
    unknown: set[str] = set()
    back = mapping.deobfuscate(obf, unknown)
    assert back == readable
    assert not unknown


def test_mapping_version_present(mapping):
    assert mapping.version.startswith("7.")
    assert len(mapping) > 1400


# ---- address math --------------------------------------------------------


def test_portal_and_booster_known_vector():
    a = UniverseAddress(galaxy=0, x=100, y=-3, z=-500, system=0x1AB, planet=1)
    assert a.portal() == "11AB7E60D865"
    assert a.booster() == "0863:007C:060B:01AB"
    assert UniverseAddress.from_portal("11AB7E60D865") == a
    assert UniverseAddress.from_booster("0863:007C:060B:01AB", planet=1) == a


def test_packed_roundtrip_and_hex_string():
    a = UniverseAddress(galaxy=0, x=-1278, y=-7, z=1201, system=134, planet=3)
    packed = a.packed()
    assert UniverseAddress.from_packed(packed) == a
    assert UniverseAddress.from_packed(hex(packed)) == a
    assert UniverseAddress.from_packed(f"0x{packed:X}") == a


def test_portal_validation():
    with pytest.raises(ValueError):
        UniverseAddress.from_portal("ZZZ")
    with pytest.raises(ValueError):
        UniverseAddress.from_booster("nope")


def test_distances():
    a = UniverseAddress(0, 0, 0, 0, 1)
    b = UniverseAddress(0, 3, 0, 4, 1)
    assert a.distance_ly(b) == 5 * 400
    assert a.distance_to_centre_ly() == 0
    assert a.galaxy_name() == "Euclid"
    assert len(a.glyph_names()) == 12


# ---- locate + model ------------------------------------------------------


def test_list_and_newest(env_save_dir):
    saves = list_saves()
    assert [s.label for s in saves] == ["slot 1 manual", "slot 1 auto"]
    assert saves[0].platform == "steam"
    assert newest_save().path.name == "save.hg"
    assert newest_save(slot=1).kind == "manual"


def test_snapshot_core(env_save_dir, mapping):
    snap = load_snapshot(newest_save().path, mapping)
    assert snap.units == 1_000_000
    assert snap.nanites == 250
    assert snap.quicksilver == 40
    assert snap.game_mode == "Normal"
    assert snap.has_nexus_access is True
    assert snap.address.portal() == "11AB7E60D865"
    assert snap.previous_address and snap.previous_address.system == 12
    assert not snap.unknown_keys


def test_inventories_and_modules(env_save_dir, mapping):
    snap = load_snapshot(newest_save().path, mapping)
    invs = {i.owner: i for i in snap.inventories()}
    assert "exosuit tech" in invs
    tech = invs["exosuit tech"]
    classes = {s.id: s.module_class for s in tech.upgrade_modules}
    assert classes == {"^UP_JET4#12345": "S", "^UP_HAZ2#99": "B"}
    assert [s.name for s in tech.damaged] == ["Hazard Protection upgrade"]
    ships = snap.ships()
    assert len(ships) == 1
    assert ships[0]["archetype"] == "Hauler"
    assert ships[0]["class"] == "A"
    assert "X-class Hyperdrive upgrade" in ships[0]["upgrades"]
    assert "S-class Hyperdrive upgrade" in ships[0]["upgrades"]
    mts = snap.multitools()
    assert mts[0]["active"] is True and mts[0]["base_stats"] == {"mining": 1.5}


def test_find_items(env_save_dir, mapping):
    snap = load_snapshot(newest_save().path, mapping)
    hits = snap.find_items("ferrite")
    assert {inv.owner for inv, _ in hits} == {"exosuit", "exosuit cargo", "grave"}
    assert sum(s.amount for _, s in hits) == 1799
    assert snap.find_items("gold")[0][0].owner == "storage 1"


def test_discovery_backlog_counts_only_own(env_save_dir, mapping):
    snap = load_snapshot(newest_save().path, mapping)
    b = snap.discovery_backlog()
    assert b["total_records"] == 9
    assert b["own_records"] == 8
    assert b["pending_upload"] == 3
    assert b["pending_by_type"] == {"Animal": 1, "Planet": 1, "Mineral": 1} or set(b["pending_by_type"]) == {"Animal", "Planet", "Mineral"}
    assert b["pending_systems"] == 1


def test_bases_teleporters_fleet_settlements_missions(env_save_dir, mapping):
    snap = load_snapshot(newest_save().path, mapping)
    bases = snap.bases()
    assert [b["name"] for b in bases] == ["Home"]  # UITempShipBase filtered out
    assert bases[0]["address"]["portal"] == "11AB7E60D865"
    assert snap.teleporters()[0]["favourite"] is True
    fr = snap.frigates()
    assert fr[0]["traits"] == ["^TRADE_PRI"]
    exps = snap.fleet_expeditions(now=1_790_000_000)
    assert exps[0]["complete"] is False and exps[0]["seconds_remaining"] == 3600
    assert exps[0]["category"] == "Trade"
    sets = snap.settlements()
    assert len(sets) == 1 and sets[0]["pending_judgement"] == "Dispute" and sets[0]["buildings_in_progress"] == 1
    assert snap.missions_in_progress() == [{"id": "^ACTIVE", "stage": 2, "seed": 9, "data": 0}]
    assert snap.recurring_missions()[0]["id"] == "^DM_QS_REWARDS"
    assert snap.known()["technology"] == ["Jetpack", "Hyperdrive"]
