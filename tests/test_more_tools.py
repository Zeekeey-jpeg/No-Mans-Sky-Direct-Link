"""Galaxy, route, progress and companion tools against the synthetic save."""

from __future__ import annotations

import json

import pytest

from nms_direct_link import history, server
from nms_direct_link.galaxy import Atlas, normalise_biome
from nms_direct_link.save import load_snapshot, newest_save


@pytest.fixture
def fresh(env_save_dir):
    server.store._snapshot = None
    server.store._snapshot_key = None
    return server.store


async def _call(tool, **params):
    res = await server.mcp.call_tool(tool, {"params": params})
    return "".join(getattr(b, "text", "") for b in res.content)


async def _json(tool, **params):
    return json.loads(await _call(tool, response_format="json", **params))


def test_atlas_biomes_names_and_bases(env_save_dir, mapping):
    a = Atlas(load_snapshot(newest_save().path, mapping))
    home = a.find_system("Testa Major")
    assert home is not None and home.name == "Testa Major"
    p1 = home.planets[1]
    assert p1.biome == "Frozen" and p1.infested and p1.name == "Verdant Prime" and p1.base_names == ["Home"]
    assert home.planets[2].biome == "Frozen"
    assert a.find_system("home") is home  # by base name
    assert a.find_system("11AB7E60D865") is home  # by portal
    assert normalise_biome("ocean") == "Waterworld" and normalise_biome("nope") is None


async def test_search_planets(fresh):
    d = await _json("nms_search_planets", biome="frozen")
    assert d["total"] == 2 and d["results"][0]["distance_ly"] == 0
    d = await _json("nms_search_planets", infested=True)
    assert [r["planet"] for r in d["results"]] == ["Verdant Prime"]
    d = await _json("nms_search_planets", with_base=True)
    assert d["results"][0]["bases"] == ["Home"]
    assert (await _call("nms_search_planets", biome="plaid")).startswith("Error:")


async def test_nearby_system_base_stats(fresh):
    rows = (await _json("nms_whats_nearby", count=5))["systems"]
    assert rows[0]["here"] is True and rows[0]["label"] == "Testa Major"
    lava = (await _json("nms_whats_nearby", biome="lava"))["systems"]
    assert len(lava) == 1 and lava[0]["distance_ly"] == 400
    sysd = await _json("nms_get_system", query="here")
    assert sysd["name"] == "Testa Major" and sysd["pending_upload"] >= 1
    base = await _json("nms_get_base", name="ho")
    assert base["name"] == "Home" and base["distance_ly"] == 0
    stats = await _json("nms_get_galaxy_stats")
    assert stats["biomes"]["Frozen"] == 2 and stats["infested_planets"] == 1 and stats["named_systems"] == 1


async def test_route(fresh):
    r = await _json("nms_plan_route", biome="lava", warp_range=500)
    assert r["stops"] == 1 and r["legs"][0]["jumps"] == 1
    r = await _json("nms_plan_route", targets=["000C7E60D866"], warp_range=100)
    assert r["legs"][0]["jumps"] == 4 and "uncharted" in r["legs"][0]["note"]
    r = await _json("nms_plan_route", targets=["nowhere"])
    assert r["missing"] == ["nowhere"]
    assert (await _call("nms_plan_route")).startswith("Error:")


async def test_stats_standing_trade_records(fresh):
    s = await _json("nms_get_player_stats")
    assert s["stats"]["DIST_WARP"]["value"] == 42 and s["stats"]["DEATHS"]["value"] == 1 and "TUTORIAL" not in s["stats"]
    st = await _json("nms_get_standing")
    assert st["standing"]["Gek"] == 6 and st["standing"]["Vy'keen"] == 2 and st["standing"]["Autophage"] == 3
    assert st["words_known"]["Gek"] == 2 and st["words_known"]["Korvax"] == 1
    tl = await _json("nms_get_trade_log")
    assert len(tl["systems"]) == 1 and tl["systems"][0]["saturated"] == ["Magnetised Ferrite"]
    rec = await _json("nms_get_records")
    assert rec["records"]["planet"][0]["record"] == "Hottest planet"


async def test_companions_hangar_waypoints_timers(fresh):
    c = await _json("nms_get_companions")
    assert c["companions"][0]["name"] == "Biscuit" and c["battle_team_slots"] == [1] and c["unlocked_slots"] == 2
    h = await _json("nms_get_hangar")
    assert h["ship_slots_used"] == 1 and h["ships"][0]["archetype"] == "Hauler"
    w = await _json("nms_get_waypoints")
    assert w["grave"]["items"] == ["99 Ferrite Dust"] and w["mission_markers"][0]["building"] == "DistressSignal"
    assert w["visited_systems_count"] == 2
    t = await _json("nms_get_timers")
    whats = " ".join(i["what"] for i in t["items"])
    assert "Item grave" in whats and "judgement" in whats and "discoveries waiting" in whats


async def test_session_history_and_changes(fresh, mapping):
    out = await _call("nms_get_session_changes")
    assert "No earlier session" in out  # only one save recorded so far
    snap = load_snapshot(newest_save().path, mapping)
    old = history.summarise(snap)
    old.update({"nanites": 100, "save_modified": "2000-01-01T00:00:00+00:00", "items": {}})
    p = history.history_path()
    p.write_text(json.dumps(old) + "\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    d = await _json("nms_get_session_changes", compare_to="first")
    assert d["changes"]["nanites"] == {"before": 100, "after": 250, "change": 150}
    assert d["items_changed"]["^LAND1"] > 0
    prog = await _json("nms_get_progress_history")
    assert len(prog["sessions"]) == 2
    auto = await _json("nms_get_session_changes", compare_to="autosave")
    assert auto["changes"]["nanites"]["change"] == 249


def test_history_can_be_disabled(monkeypatch, env_save_dir, mapping):
    monkeypatch.setenv("NMS_NO_HISTORY", "1")
    assert history.record(load_snapshot(newest_save().path, mapping)) is None
    assert not history.history_path().exists()


async def test_resources(fresh):
    stats = list(await server.mcp.read_resource("nms://galaxy/stats"))
    assert json.loads(stats[0].content)["systems"] >= 2
    bases = list(await server.mcp.read_resource("nms://bases"))
    assert json.loads(bases[0].content)[0]["name"] == "Home"


def test_corrupt_history_never_breaks_reads(env_save_dir, monkeypatch):
    p = history.history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xfe\x00garbage\n{not json\n[1,2,3]\n")
    server.store._snapshot = None
    server.store._snapshot_key = None
    snap = server.store.snapshot()
    assert snap.nanites == 250
    monkeypatch.setattr(history, "summarise", lambda s: 1 / 0)
    server.store._snapshot = None
    server.store._snapshot_key = None
    assert server.store.snapshot().nanites == 250
