"""Exercise the MCP tools end-to-end through the FastMCP server against the synthetic save."""

from __future__ import annotations

import json

import pytest

from nms_direct_link import server


@pytest.fixture
def fresh_store(env_save_dir):
    server.store._snapshot = None
    server.store._snapshot_key = None
    return server.store


async def _call(name: str, **args):
    result = await server.mcp.call_tool(name, args)
    return "".join(getattr(b, "text", "") for b in result.content)


async def test_tool_registry_names():
    tools = await server.mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted([
        "nms_list_saves", "nms_get_player_state", "nms_get_location", "nms_convert_coordinates", "nms_audit_tech",
        "nms_find_item", "nms_get_discovery_backlog", "nms_get_fleet_status", "nms_get_settlements", "nms_get_missions",
        "nms_plan_nanites", "nms_explain", "nms_get_community_mission",
        "nms_search_planets", "nms_plan_route", "nms_get_system", "nms_get_base", "nms_whats_nearby", "nms_get_galaxy_stats",
        "nms_get_player_stats", "nms_get_standing", "nms_get_trade_log", "nms_get_records", "nms_get_companions",
        "nms_get_hangar", "nms_get_waypoints", "nms_get_timers", "nms_get_session_changes", "nms_get_progress_history",
        "nms_look_at_screen", "nms_read_screenshots", "nms_log_shop", "nms_find_in_shops", "nms_get_shops_here",
        "nms_station_brief", "nms_upgrade_plan", "nms_best_prices",
    ])
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint is (t.name != "nms_log_shop")
        assert t.annotations.destructive_hint is (t.name == "nms_log_shop")


async def test_list_saves(fresh_store):
    out = await _call("nms_list_saves", params={})
    assert "slot 1 manual" in out and "slot 1 auto" in out


async def test_player_state_markdown_and_json(fresh_store):
    md = await _call("nms_get_player_state", params={})
    assert "Nanites:** 250" in md and "11AB7E60D865" in md
    js = json.loads(await _call("nms_get_player_state", params={"response_format": "json"}))
    assert js["currencies"] == {"units": 1_000_000, "nanites": 250, "quicksilver": 40}
    assert js["location"]["portal"] == "11AB7E60D865"


async def test_slot_selection(fresh_store):
    js = json.loads(await _call("nms_get_player_state", params={"slot": 1, "response_format": "json"}))
    assert js["currencies"]["nanites"] == 250  # newest in slot 1 is the manual save


async def test_location_and_convert(fresh_store):
    out = await _call("nms_get_location", params={})
    assert "Home" in out and "Teleporter network" in out
    js = json.loads(await _call("nms_convert_coordinates", params={"portal": "11AB7E60D865", "response_format": "json"}))
    assert js["signal_booster"] == "0863:007C:060B:01AB"
    assert js["distance_from_player_ly"] == 0
    err = await _call("nms_convert_coordinates", params={})
    assert err.startswith("Error:")


async def test_audit_find_backlog(fresh_store):
    audit = await _call("nms_audit_tech", params={})
    assert "Test Hauler" in audit and "S-class Hyperdrive upgrade" in audit and "damaged" in audit
    find = await _call("nms_find_item", params={"query": "chromatic"})
    assert "freighter" in find and "2,500" in find
    none = await _call("nms_find_item", params={"query": "unobtainium"})
    assert none.startswith("No inventory")
    backlog = json.loads(await _call("nms_get_discovery_backlog", params={"response_format": "json"}))
    assert backlog["pending_upload"] == 3


async def test_fleet_settlements_missions(fresh_store):
    fleet = await _call("nms_get_fleet_status", params={})
    assert "Sunrise" in fleet and "Trade" in fleet
    sets = await _call("nms_get_settlements", params={})
    assert "Testville" in sets and "Dispute" in sets
    missions = await _call("nms_get_missions", params={})
    assert "^ACTIVE" in missions and "^DM_QS_REWARDS" in missions


async def test_nanite_plan(fresh_store):
    out = await _call("nms_plan_nanites", params={"target": 5000})
    assert "gap 4,750" in out
    assert "Upload pending discoveries" in out
    assert "Runaway Mould" in out
    assert "Not yet available" in out  # ship scrap needs 20M units, we have 1M
    js = json.loads(await _call("nms_plan_nanites", params={"target": 100, "response_format": "json"}))
    assert js["gap"] == 0


async def test_explain():
    out = await _call("nms_explain", params={"topic": "S-class"})
    assert "S-class" in out
    out = await _call("nms_explain", params={"topic": "hyperdrive"})
    assert "Cadmium" in out
    out = await _call("nms_explain", params={"topic": "definitely-unknown"})
    assert out.startswith("No explainer")


async def test_no_save_error(monkeypatch, tmp_path):
    monkeypatch.setenv("NMS_SAVE_DIR", str(tmp_path))
    server.store._snapshot = None
    out = await _call("nms_get_player_state", params={})
    assert out.startswith("Error:") and "NMS_SAVE_DIR" in out


async def test_resource(fresh_store):
    contents = list(await server.mcp.read_resource("nms://player/state"))
    assert json.loads(contents[0].content)["currencies"]["nanites"] == 250
