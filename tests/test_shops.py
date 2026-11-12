"""Shop Scanner: capture (mocked), screenshots folder, log, search, quick view."""

from __future__ import annotations

import json
import os
import time

import pytest

from nms_direct_link import server, shops


@pytest.fixture
def fresh(env_save_dir):
    server.store._snapshot = None
    server.store._snapshot_key = None
    return server.store


def _png(path, color=(200, 80, 30)):
    from PIL import Image

    Image.new("RGB", (2000, 1000), color).save(path)


async def _raw(tool, **params):
    return await server.mcp.call_tool(tool, {"params": params})


def _text(res):
    return "".join(getattr(b, "text", "") or "" for b in res.content)


async def test_look_at_screen_returns_image(fresh, monkeypatch, tmp_path):
    from PIL import Image

    img = Image.new("RGB", (3000, 1500), (10, 20, 30))
    grabs = []
    monkeypatch.setattr("PIL.ImageGrab.grab", lambda **kw: grabs.append(kw) or img)
    monkeypatch.setattr(shops, "_find_game_window", lambda: None)
    res = await _raw("nms_look_at_screen")  # game not found: must NOT fall back to the desktop
    assert [b.type for b in res.content] == ["text"] and "window not found" in res.content[0].text and grabs == []
    monkeypatch.setattr(shops, "_find_game_window", lambda: (0, 0, 1920, 1080))
    res = await _raw("nms_look_at_screen")
    assert grabs[-1]["bbox"] == (0, 0, 1920, 1080) and grabs[-1]["all_screens"] is False
    res_screen = await _raw("nms_look_at_screen", target="screen")
    assert grabs[-1]["bbox"] is None and [b.type for b in res_screen.content] == ["text", "image"]
    kinds = [b.type for b in res.content]
    assert kinds == ["text", "image"]
    assert "11AB7E60D865" in res.content[0].text and "nms_log_shop" in res.content[0].text
    assert res.content[1].mime_type == "image/jpeg"


async def test_read_screenshots(fresh, tmp_path):
    shots = tmp_path / "shots"
    assert shops.steam_screenshot_dirs() == []  # explicit dir that doesn't exist: no fallback to real Steam folders
    assert "Press F12" in _text(await _raw("nms_read_screenshots"))
    shots.mkdir()
    assert shops.steam_screenshot_dirs() == [shots]
    res = await _raw("nms_read_screenshots")
    assert "Press F12" in _text(res)
    _png(shots / "a.png")
    _png(shots / "b.jpg")
    old = time.time() - 10 * 3600
    os.utime(shots / "a.png", (old, old))
    res = await _raw("nms_read_screenshots", within_minutes=60)
    assert [b.type for b in res.content] == ["text", "text", "image"]
    res = await _raw("nms_read_screenshots", within_minutes=24 * 60)
    assert sum(1 for b in res.content if b.type == "image") == 2


async def test_log_find_and_quick_view(fresh):
    out = _text(await _raw("nms_log_shop", merchant="Technology Merchant", station="Testa Station", items=[
        {"name": "Hyperdrive Upgrade", "item_class": "S", "category": "hyperdrive upgrade", "price": 520, "currency": "nanites"},
        {"name": "Pulse Engine Upgrade", "item_class": "A", "price": 310, "currency": "nanites"},
        {"name": "Warp Cell", "price": 46000, "currency": "units"},
    ]))
    assert "Logged 3 item(s)" in out
    found = json.loads(_text(await _raw("nms_find_in_shops", query="hyperdrive", item_class="S", max_price=600, response_format="json")))
    assert len(found["results"]) == 1 and found["results"][0]["station"] == "Testa Station" and found["results"][0]["distance_ly"] == 0
    assert "No match" in _text(await _raw("nms_find_in_shops", item_class="X"))
    # re-log replaces
    out = _text(await _raw("nms_log_shop", merchant="technology merchant", items=[{"name": "Hyperdrive Upgrade", "item_class": "B", "price": 140, "currency": "nanites"}]))
    assert "replaced" in out
    here = json.loads(_text(await _raw("nms_get_shops_here", response_format="json")))
    assert len(here["shops"]) == 1 and here["shops"][0]["items"][0]["item_class"] == "B"
    md = _text(await _raw("nms_get_shops_here"))
    assert "Technology Merchant" in md and "B-class Hyperdrive Upgrade" in md


async def test_log_elsewhere_by_portal(fresh):
    _text(await _raw("nms_log_shop", merchant="starship outfitter", portal="000C7E60D866", items=[{"name": "Fighter", "item_class": "S", "price": 9_000_000, "currency": "units"}]))
    rows = json.loads(_text(await _raw("nms_find_in_shops", merchant="outfitter", response_format="json")))["results"]
    assert rows[0]["portal"] == "000C7E60D866" and rows[0]["distance_ly"] == 400
    assert "No shops scanned" in _text(await _raw("nms_get_shops_here"))


async def test_shop_tool_annotations():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    log = tools["nms_log_shop"].annotations
    assert log.read_only_hint is False
    assert log.destructive_hint is True  # re-logging replaces the earlier list
    assert log.idempotent_hint is False
    assert log.open_world_hint is False
    for n in ("nms_look_at_screen", "nms_read_screenshots", "nms_find_in_shops", "nms_get_shops_here"):
        ann = tools[n].annotations
        assert ann.read_only_hint is True
        assert ann.destructive_hint is False
        assert ann.idempotent_hint is True
        assert ann.open_world_hint is False
