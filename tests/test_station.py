"""Station brief, upgrade plan and price memory against the synthetic save."""

from __future__ import annotations

import json

import pytest

from nms_direct_link import server


@pytest.fixture
def fresh(env_save_dir):
    server.store._snapshot = None
    server.store._snapshot_key = None
    return server.store


async def _call(tool, **params):
    res = await server.mcp.call_tool(tool, {"params": params})
    return "".join(getattr(b, "text", "") or "" for b in res.content)


async def _json(tool, **params):
    return json.loads(await _call(tool, response_format="json", **params))


async def test_upgrade_plan_gaps(fresh):
    p = await _json("nms_upgrade_plan")
    by = {s["upgrade"]: s for s in p["steps"]}
    hyp = by["Hyperdrive"]
    assert hyp["installed"] == ["X", "S"] and hyp["free_slots"] == 1 and hyp["group"] == "starship"
    jet = by["Movement System (jetpack)"]
    assert jet["installed"] == ["S"] and jet["free_slots"] == 2
    haz = by["Hazard Protection"]
    assert haz["installed"] == ["B"] and "replace B with S" in haz["action"] and "2 free slots" in haz["action"]
    assert p["nanites"] == 250 and p["planned_spend"] == 0  # 250 nanites can't buy a ~500 S-class module
    rich = await _json("nms_upgrade_plan", budget_nanites=2000)
    assert rich["planned_spend"] > 0


async def test_station_brief_and_prices(fresh):
    b = await _json("nms_station_brief")
    assert b["system"] == "01AB7E60D865" and b["open_first"] == "technology merchant"
    assert not b["scanned_shops_here"] and len(b["merchants"]) == 7
    assert b["trade_here"]["saturated"] == ["Magnetised Ferrite"]
    await _call("nms_log_shop", merchant="technology merchant", items=[
        {"name": "Hyperdrive Upgrade", "item_class": "S", "price": 480, "currency": "nanites"},
        {"name": "Warp Cell", "price": 46000, "currency": "units"}])
    await _call("nms_log_shop", merchant="galactic trade terminal", portal="000C7E60D866", items=[
        {"name": "Warp Cell", "price": 41000, "currency": "units"}])
    b = await _json("nms_station_brief")
    assert b["scanned_shops_here"][0]["merchant"] == "technology merchant"
    assert next(m for m in b["merchants"] if m["merchant"] == "technology merchant")["scanned_here"] is True
    md = await _call("nms_station_brief")
    assert "Don't sell here again yet" in md and "Open first" in md
    plan = await _json("nms_upgrade_plan")
    hyp = next(s for s in plan["steps"] if s["upgrade"] == "Hyperdrive")
    assert hyp["best_seen"]["price"] == 480 and hyp["estimated_nanites"] == 480
    prices = (await _json("nms_best_prices", query="warp"))["items"]
    assert prices[0]["cheapest"] == 41000 and prices[0]["highest"] == 46000 and prices[0]["times_seen"] == 2
    assert prices[0]["where"] == "000C7E60D866"
    assert "No priced items" in await _call("nms_best_prices", query="unobtainium")


def _snap_with(mapping, mutate):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from conftest import readable_save
    from nms_direct_link.save.model import SaveSnapshot

    data = readable_save()
    mutate(data["BaseContext"]["PlayerStateData"])
    return SaveSnapshot(data, mapping=mapping)


def _slot(item_id, x=0):
    return {"Type": {"InventoryType": "Technology"}, "Id": item_id, "Amount": 1, "MaxAmount": 1, "DamageFactor": 0.0,
            "FullyInstalled": True, "Index": {"X": x, "Y": 0}}


def _inv(slots):
    return {"Slots": slots, "ValidSlotIndices": [{"X": i, "Y": 0} for i in range(10)], "Class": {"InventoryClass": "S"},
            "BaseStatValues": [], "Width": 10, "Height": 1}


def test_plan_uses_active_multitool_and_exact_primary_ship(mapping):
    from nms_direct_link.planner import upgrade_gaps

    def mutate(p):
        p["Multitools"] = [
            {"Name": "Old", "Store": _inv([_slot("^SCAN1"), _slot("^UP_SCAN4#1", 1), _slot("^UP_SCAN4#2", 2), _slot("^UP_SCAN4#3", 3)])},
            {"Name": "New", "Store": _inv([_slot("^SCAN1")])},
        ]
        p["ActiveMultioolIndex"] = 1
        ships = [{"Name": f"ship {i + 1}", "Resource": {"Filename": "FIGHTER", "Seed": [True, "0x1"]},
                  "Inventory": _inv([]), "Inventory_TechOnly": _inv([_slot("^HYPERDRIVE")]), "Inventory_Cargo": _inv([])} for i in range(10)]
        ships[9]["Inventory_TechOnly"] = _inv([_slot("^HYPERDRIVE"), _slot("^UP_HYP4#1", 1), _slot("^UP_HYP4#2", 2), _slot("^UP_HYP4#3", 3)])
        p["ShipOwnership"] = ships
        p["PrimaryShip"] = 0

    gaps = {g["family"]: g for g in upgrade_gaps(_snap_with(mapping, mutate))}
    assert gaps["UP_SCAN"]["installed"] == [] and gaps["UP_SCAN"]["free_slots"] == 3
    assert gaps["UP_HYP"]["installed"] == [] and gaps["UP_HYP"]["complete"] is False


async def test_shop_match_stays_in_family(fresh):
    await _call("nms_log_shop", merchant="technology merchant", items=[
        {"name": "Freighter Hyperdrive Upgrade", "item_class": "S", "price": 10, "currency": "nanites"},
        {"name": "Hyperdrive Upgrade", "item_class": "A", "price": 300, "currency": "nanites"}])
    plan = await _json("nms_upgrade_plan")
    hyp = next(s for s in plan["steps"] if s["upgrade"] == "Hyperdrive")
    assert hyp["best_seen"]["name"] == "Hyperdrive Upgrade" and hyp["estimated_nanites"] == 300
    assert hyp["modules_needed"] == 1 and hyp["estimated_total"] == 300
