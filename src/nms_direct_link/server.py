"""No Man's Sky Direct Link — MCP server.

Run ``nms-direct-link`` for stdio (what Claude Desktop / Claude Code expect). All tools are read-only.
Logging goes to stderr so stdout stays clean for the protocol.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC
from enum import StrEnum
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .community import fetch_community_mission
from .knowledge import KNOWLEDGE_CHECKED, NANITE_METHODS, UPGRADE_CLASSES, explain, topics
from .save import UniverseAddress, list_saves
from .save.model import SaveSnapshot
from .store import NoSaveFound, SaveStore

log = logging.getLogger("nms_direct_link")

mcp = MCPServer(
    "nms_direct_link",
    instructions=(
        "Read-only view of the player's No Man's Sky save. Call nms_get_player_state first for balances and location, "
        "then the specific tool you need. Data is as fresh as the last save write (save point, exiting the ship, autosave)."
    ),
)
store = SaveStore()

READ_ONLY = {"read_only_hint": True, "destructive_hint": False, "idempotent_hint": True, "open_world_hint": False}
READ_ONLY_NET = {**READ_ONLY, "open_world_hint": True}


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


class FormatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    slot: int | None = Field(default=None, ge=1, le=15, description="Save slot (1-15). Default: the most recently written save.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' (default) or 'json'.")


def _snap(slot: int | None) -> SaveSnapshot:
    return store.snapshot(slot)


def _err(msg: str) -> str:
    return f"Error: {msg}"


def _fmt(data: Any, fmt: ResponseFormat, md: str) -> str:
    return json.dumps(data, indent=2, default=str) if fmt == ResponseFormat.JSON else md


def _n(v: int | float | None) -> str:
    return f"{v:,}" if isinstance(v, (int, float)) else "?"



def _ly(v) -> str:
    """Distances come from region (voxel) coordinates: 0 between different stars means 'same region'."""
    if v is None:
        return "? ly"
    return "same region" if v == 0 else f"~{v:,} ly"


def _age(snap: SaveSnapshot) -> str:
    if not snap.modified:
        return "unknown"
    from datetime import datetime

    secs = int((datetime.now(tz=UTC) - snap.modified).total_seconds())
    if secs < 90:
        return f"{secs}s ago"
    if secs < 5400:
        return f"{secs // 60} min ago"
    return f"{secs / 3600:.1f} h ago"


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------


class ListSavesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(name="nms_list_saves", annotations=ToolAnnotations(title="List save files", **READ_ONLY))
async def nms_list_saves(params: ListSavesInput) -> str:
    """List every No Man's Sky save file found on this machine (Steam and GOG folders, or NMS_SAVE_DIR), newest first.

    Returns slot, manual/auto, platform, modification time and size for each. Use it to confirm the server
    sees the right save before asking about state. No game data is read.
    """
    try:
        saves = list_saves()
    except OSError as exc:
        return _err(f"could not scan save folders: {exc}")
    if not saves:
        return _err("no saves found. Set NMS_SAVE_DIR to your HelloGames\\NMS\\<account> folder.")
    data = [s.to_dict() for s in saves]
    lines = ["# Save files (newest first)", ""]
    for s in saves:
        lines.append(f"- **{s.label}** · {s.platform} · {s.modified:%Y-%m-%d %H:%M} UTC · {s.size // 1024} KiB · `{s.path}`")
    return _fmt(data, params.response_format, "\n".join(lines))


@mcp.tool(name="nms_get_player_state", annotations=ToolAnnotations(title="Player state", **READ_ONLY))
async def nms_get_player_state(params: FormatInput) -> str:
    """Core snapshot: units, nanites, quicksilver, game mode, play time, current location (glyphs, coordinates,
    distance to centre), health, Nexus access, current mission, and how old the save is.

    Start here. Everything else refines this view.
    """
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    s = snap.summary()
    loc = snap.address
    md = "\n".join(
        [
            f"# Player state — {snap.game_mode} mode · save written {_age(snap)}",
            "",
            f"- **Units:** {_n(snap.units)}  · **Nanites:** {_n(snap.nanites)}  · **Quicksilver:** {_n(snap.quicksilver)}",
            f"- **Play time:** {s['play_time_hours']} h · **Nexus access:** {'yes' if snap.has_nexus_access else 'no'} · **Glyphs known:** {snap.known_glyphs}/16",
            f"- **Location:** {loc.galaxy_name()}, planet index {loc.planet} of system {loc.system} · portal `{loc.portal()}` · booster `{loc.booster()}`",
            f"- **Glyph sequence:** {' · '.join(loc.glyph_names())}",
            f"- **Distance to galactic centre:** {_ly(round(loc.distance_to_centre_ly()))}",
            f"- **Health:** {snap.health.get('health')} · shield {snap.health.get('shield')} · ship health {snap.health.get('ship_health')}",
            f"- **Current mission:** `{snap.current_mission().get('id')}`",
            "",
            f"_Save: {snap.path.name if snap.path else '?'} v{snap.version} · mapping libMBIN {snap.mapping.version if snap.mapping else '?'} · "
            f"{len(snap.unknown_keys)} unmapped keys_",
        ]
    )
    return _fmt(s, params.response_format, md)


@mcp.tool(name="nms_get_location", annotations=ToolAnnotations(title="Where am I", **READ_ONLY))
async def nms_get_location(params: FormatInput) -> str:
    """Current, previous and freighter locations with every coordinate form (voxel, portal glyphs, signal booster,
    packed address) plus your bases and teleporter endpoints with distances from where you are."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    here = snap.address
    prev = snap.previous_address
    fr = snap.freighter_address
    bases = snap.bases()
    tele = snap.teleporters()
    for b in bases:
        if b["address"]:
            b["distance_ly"] = round(here.distance_ly(UniverseAddress.from_packed(b["address"]["packed"])))
    for t in tele:
        if t["address"]:
            t["distance_ly"] = round(here.distance_ly(UniverseAddress.from_packed(t["address"]["packed"])))
    data = {"current": here.to_dict(), "previous": prev.to_dict() if prev else None, "freighter": fr.to_dict() if fr else None,
            "bases": bases, "teleporters": tele}
    lines = ["# Location", "", f"**Now:** {here}", f"- glyphs: {' · '.join(here.glyph_names())}",
             f"- voxel ({here.x}, {here.y}, {here.z}) system {here.system} · {_ly(round(here.distance_to_centre_ly()))} from centre"]
    if prev:
        lines.append(f"**Previous:** {prev} ({_ly(round(here.distance_ly(prev)))} away)")
    if fr:
        lines.append(f"**Freighter:** {fr} ({_ly(round(here.distance_ly(fr)))} away)")
    if bases:
        lines += ["", "## Bases"]
        for b in bases:
            lines.append(f"- **{b['name']}** ({b['type']}, {b['objects']} parts) — {b['address']['portal'] if b['address'] else '?'} · {_ly(b.get('distance_ly'))}")
    if tele:
        lines += ["", "## Teleporter network"]
        for t in tele[:25]:
            lines.append(f"- {t['name']} [{t['type']}] — {t['address']['portal'] if t['address'] else '?'} · {_ly(t.get('distance_ly'))}")
        if len(tele) > 25:
            lines.append(f"- … {len(tele) - 25} more (use response_format='json')")
    return _fmt(data, params.response_format, "\n".join(lines))


class ConvertInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    portal: str | None = Field(default=None, description="12 hex glyphs, e.g. '11AB7E60D865'", max_length=20)
    booster: str | None = Field(default=None, description="Signal booster code 'XXXX:YYYY:ZZZZ:SSSS'", max_length=24)
    packed: str | None = Field(default=None, description="Packed u64 address as decimal or 0x-hex", max_length=24)
    voxel_x: int | None = Field(default=None, ge=-2048, le=2047)
    voxel_y: int | None = Field(default=None, ge=-128, le=127)
    voxel_z: int | None = Field(default=None, ge=-2048, le=2047)
    system_index: int | None = Field(default=None, ge=0, le=4095)
    planet_index: int = Field(default=0, ge=0, le=15)
    galaxy: int = Field(default=0, ge=0, le=255, description="Galaxy index (0 = Euclid)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(name="nms_convert_coordinates", annotations=ToolAnnotations(title="Convert coordinates", **READ_ONLY))
async def nms_convert_coordinates(params: ConvertInput) -> str:
    """Convert between portal glyphs, signal-booster codes, packed addresses and voxel coordinates.
    Give exactly one of: portal, booster, packed, or the voxel_x/voxel_y/voxel_z/system_index set.
    Also returns the distance from the player's current position when a save is available."""
    try:
        if params.portal:
            addr = UniverseAddress.from_portal(params.portal, params.galaxy)
        elif params.booster:
            addr = UniverseAddress.from_booster(params.booster, params.galaxy, params.planet_index)
        elif params.packed:
            addr = UniverseAddress.from_packed(params.packed)
        elif None not in (params.voxel_x, params.voxel_y, params.voxel_z, params.system_index):
            addr = UniverseAddress(params.galaxy, params.voxel_x, params.voxel_y, params.voxel_z, params.system_index, params.planet_index)
        else:
            return _err("provide portal, booster, packed, or all of voxel_x/voxel_y/voxel_z/system_index")
    except (ValueError, TypeError) as exc:
        return _err(str(exc))
    data = addr.to_dict()
    try:
        here = _snap(None).address
        data["distance_from_player_ly"] = round(here.distance_ly(addr))
    except Exception:  # noqa: BLE001 - distance is optional
        pass
    md = "\n".join([
        f"# {addr}", "",
        f"- portal: `{addr.portal()}` ({' · '.join(addr.glyph_names())})",
        f"- signal booster: `{addr.booster()}`",
        f"- voxel: x={addr.x} y={addr.y} z={addr.z} · system {addr.system} · planet {addr.planet} · {addr.galaxy_name()}",
        f"- packed: {addr.packed()} (0x{addr.packed():X})",
        f"- {_ly(round(addr.distance_to_centre_ly()))} from the galactic centre"
        + (f" · {_ly(data['distance_from_player_ly'])} from you" if "distance_from_player_ly" in data else ""),
    ])
    return _fmt(data, params.response_format, md)


class TechAuditInput(FormatInput):
    inventory: str = Field(default="all", description="'all', 'exosuit', 'ship', 'multitool', 'freighter', 'exocraft'", max_length=20)


@mcp.tool(name="nms_audit_tech", annotations=ToolAnnotations(title="Technology audit", **READ_ONLY))
async def nms_audit_tech(params: TechAuditInput) -> str:
    """Installed technology and upgrade modules per inventory with their class (C/B/A/S/X), damaged or
    uninstalled tech, free slots, and ship/multitool class and base stats. Use it to answer
    'what should I upgrade next' and 'is anything broken'."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    want = params.inventory.lower()
    invs = [i for i in snap.inventories() if want == "all" or want in i.owner.lower() or (want == "ship" and "(ship" in i.owner)]
    invs = [i for i in invs if i.technology or i.upgrade_modules]
    data = {"ships": snap.ships(), "multitools": snap.multitools(), "inventories": [i.to_dict() for i in invs]}
    lines = ["# Technology audit", ""]
    for sh in data["ships"]:
        lines.append(f"## Ship: {sh['name']} — {sh['class']}-class {sh['archetype']}{' (primary)' if sh['primary'] else ''}")
        lines.append(f"- stats: {sh['base_stats']} · slots {sh['general_slots']} general / {sh['tech_slots']} tech")
        lines.append(f"- tech: {', '.join(sh['tech']) or 'none'}")
        lines.append(f"- upgrades: {', '.join(sh['upgrades']) or 'none'}")
    for mt in data["multitools"]:
        lines.append(f"## Multitool: {mt['name']} — {mt['class']}-class, {mt['slots']} slots{' (active)' if mt['active'] else ''}")
        lines.append(f"- tech: {', '.join(mt['tech']) or 'none'}")
        lines.append(f"- upgrades: {', '.join(mt['upgrades']) or 'none'}")
    for inv in invs:
        if "(ship" in inv.owner or "(multitool" in inv.owner:
            continue
        lines.append(f"## {inv.owner.title()} ({inv.inventory_class or '?'}-class, {inv.free_slots} free of {inv.valid_slots})")
        for s in inv.technology:
            tag = f" [{s.module_class}]" if s.is_upgrade_module else ""
            dmg = " ⚠ damaged" if s.damage > 0 else (" ⚠ not installed" if not s.installed else "")
            lines.append(f"- {s.name}{tag}{dmg}")
    damaged = [(i.owner, s.name) for i in snap.inventories() for s in i.damaged]
    lines += ["", f"**Damaged / uninstalled tech:** {len(damaged)}" + (": " + ", ".join(f"{o} → {n}" for o, n in damaged[:12]) if damaged else "")]
    return _fmt(data, params.response_format, "\n".join(lines))


class FindItemInput(FormatInput):
    query: str = Field(..., min_length=1, max_length=60, description="Item name or ID fragment, e.g. 'warp cell', 'chromatic', 'UP_HYP'")


@mcp.tool(name="nms_find_item", annotations=ToolAnnotations(title="Find an item", **READ_ONLY))
async def nms_find_item(params: FindItemInput) -> str:
    """Search every inventory (exosuit, ships, multitools, freighter, exocraft, storage containers, cooking, grave)
    for an item by name or ID fragment and report where it is and how many you hold."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    hits = snap.find_items(params.query)
    total = sum(s.amount for _, s in hits if s.kind != "Technology")
    data = {"query": params.query, "matches": len(hits), "total_amount": total,
            "hits": [{"inventory": inv.owner, **s.to_dict()} for inv, s in hits]}
    if not hits:
        return _fmt(data, params.response_format, f"No inventory holds anything matching '{params.query}'.")
    lines = [f"# '{params.query}' — {len(hits)} hit(s), {_n(total)} total", ""]
    for inv, s in hits:
        qty = f"{_n(s.amount)}/{_n(s.max_amount)}" if s.kind != "Technology" else (f"{s.module_class}-class" if s.is_upgrade_module else "tech")
        lines.append(f"- **{s.name}** (`{s.id}`) — {inv.owner} · {qty}")
    return _fmt(data, params.response_format, "\n".join(lines))


@mcp.tool(name="nms_get_discovery_backlog", annotations=ToolAnnotations(title="Discovery upload backlog", **READ_ONLY))
async def nms_get_discovery_backlog(params: FormatInput) -> str:
    """How many of your discoveries are still waiting to be uploaded for nanites, broken down by type
    (planets, systems, fauna, flora, minerals) and how many systems they span."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    b = snap.discovery_backlog()
    lines = [f"# Discovery backlog — {_n(b['pending_upload'])} pending upload", "",
             f"- your records: {_n(b['own_records'])} ({_n(b['own_uploaded'])} uploaded) · all records in save: {_n(b['total_records'])}",
             f"- pending across {b['pending_systems']} system(s)", "", "## Pending by type"]
    for k, v in b["pending_by_type"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "_Upload from the Discoveries menu (or the Anomaly) to collect the nanites. Planet and system entries pay the most._"]
    return _fmt(b, params.response_format, "\n".join(lines))


@mcp.tool(name="nms_get_fleet_status", annotations=ToolAnnotations(title="Freighter and frigate fleet", **READ_ONLY))
async def nms_get_fleet_status(params: FormatInput) -> str:
    """Freighter (class, hyperdrive tech, location) and frigates (role, class, record) with any fleet
    expeditions in progress and their ETA."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    frigates = snap.frigates()
    exps = snap.fleet_expeditions()
    fr_tech = [i for i in snap.inventories() if i.owner == "freighter tech"]
    fr_inv = [i for i in snap.inventories() if i.owner == "freighter"]
    data = {"freighter": {"address": snap.freighter_address.to_dict() if snap.freighter_address else None,
                          "class": fr_inv[0].inventory_class if fr_inv else None,
                          "tech": [s.name for i in fr_tech + fr_inv for s in i.technology]},
            "frigates": frigates, "expeditions": exps}
    lines = ["# Fleet", ""]
    if snap.freighter_address:
        lines.append(f"**Freighter:** {data['freighter']['class'] or '?'}-class at {snap.freighter_address} · tech: {', '.join(data['freighter']['tech']) or 'none'}")
    else:
        lines.append("**Freighter:** none recorded")
    lines += ["", f"## Frigates ({len(frigates)})"]
    for f in frigates:
        lines.append(f"- {f['name']} — {f['class']}-class {f['role']} ({f['race']}) · {f['expeditions']} expeditions, {f['successes']} wins / {f['failures']} fails, damaged {f['times_damaged']}x")
    lines += ["", f"## Expeditions in progress ({len(exps)})"]
    for e in exps:
        status = "COMPLETE — debrief at the fleet command room" if e["complete"] else f"{e['seconds_remaining'] // 3600}h {(e['seconds_remaining'] % 3600) // 60}m remaining (ETA {e['eta']})"
        lines.append(f"- {e['category']} · {e['frigates']} frigates ({e['damaged']} damaged) · {status}")
    if not exps:
        lines.append("- none")
    return _fmt(data, params.response_format, "\n".join(lines))


@mcp.tool(name="nms_get_settlements", annotations=ToolAnnotations(title="Settlements", **READ_ONLY))
async def nms_get_settlements(params: FormatInput) -> str:
    """Your settlements: population, pending judgements, buildings under construction, stats and perks.
    The Stats array is reported raw; its index order is not confirmed."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    sets = snap.settlements()
    if not sets:
        return _fmt({"settlements": []}, params.response_format, "No settlement is recorded in this save.")
    lines = [f"# Settlements ({len(sets)})", ""]
    for s in sets:
        lines.append(f"## {s['name']} — population {s['population']}")
        lines.append(f"- pending judgement: {s['pending_judgement'] or 'none'} · buildings in progress: {s['buildings_in_progress']}")
        lines.append(f"- location: {s['address']['portal'] if s['address'] else '?'} · stats (raw): {s['stats']}")
    return _fmt({"settlements": sets}, params.response_format, "\n".join(lines))


@mcp.tool(name="nms_get_missions", annotations=ToolAnnotations(title="Missions", **READ_ONLY))
async def nms_get_missions(params: FormatInput) -> str:
    """Current mission, missions with progress recorded, and recurring (daily/weekly/community) mission
    deadlines from the save. IDs are the game's internal mission identifiers."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    data = {"current": snap.current_mission(), "in_progress": snap.missions_in_progress(), "recurring": snap.recurring_missions()}
    lines = ["# Missions", "", f"**Current:** `{data['current']['id']}`", "", f"## In progress ({len(data['in_progress'])})"]
    for m in data["in_progress"][:40]:
        lines.append(f"- `{m['id']}` stage {m['stage']}")
    if len(data["in_progress"]) > 40:
        lines.append(f"- … {len(data['in_progress']) - 40} more (json)")
    lines += ["", "## Recurring deadlines"]
    for r in data["recurring"]:
        lines.append(f"- `{r['id']}` → {r['deadline']}")
    return _fmt(data, params.response_format, "\n".join(lines))


class NanitePlanInput(FormatInput):
    target: int = Field(..., ge=1, le=100_000_000, description="Nanite balance you want to reach")


@mcp.tool(name="nms_plan_nanites", annotations=ToolAnnotations(title="Nanite plan", **READ_ONLY))
async def nms_plan_nanites(params: NanitePlanInput) -> str:
    """Plan how to reach a nanite target from your current balance: counts your free nanites (pending discovery
    uploads), then ranks farming methods you can actually do given your units, Nexus access and progress.
    Rates are community estimates, labelled as such."""
    try:
        snap = _snap(params.slot)
    except (NoSaveFound, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    have = snap.nanites
    gap = max(params.target - have, 0)
    backlog = snap.discovery_backlog()
    pending = backlog["pending_upload"]
    steps: list[dict[str, Any]] = []
    if pending:
        steps.append({"step": "Upload pending discoveries", "detail": f"{pending} records waiting ({backlog['pending_by_type']}). Free nanites, no travel.",
                      "estimate": "varies; planets and systems pay most"})
    methods = []
    for m in NANITE_METHODS:
        ok = True
        why = []
        if m.needs_units and snap.units < m.needs_units:
            ok = False
            why.append(f"needs ~{_n(m.needs_units)} units (you have {_n(snap.units)})")
        if m.needs_nexus and not snap.has_nexus_access:
            ok = False
            why.append("needs Anomaly access")
        methods.append({"key": m.key, "name": m.name, "rate_per_hour_estimate": list(m.rate_per_hour), "requires": m.requires,
                        "how": m.how, "available_now": ok, "blocked_by": why, "tags": list(m.tags)})
    avail = [m for m in methods if m["available_now"] and m["rate_per_hour_estimate"][1] > 0]
    avail.sort(key=lambda m: -m["rate_per_hour_estimate"][1])
    data = {"have": have, "target": params.target, "gap": gap, "pending_discoveries": pending, "steps": steps, "methods": methods,
            "knowledge_checked": KNOWLEDGE_CHECKED}
    lines = [f"# Nanite plan: {_n(have)} → {_n(params.target)} (gap {_n(gap)})", ""]
    if gap == 0:
        lines.append("You already have enough nanites.")
    for s in steps:
        lines.append(f"1. **{s['step']}** — {s['detail']}")
    if gap and avail:
        best = avail[0]
        lo, hi = best["rate_per_hour_estimate"]
        hours = f"~{gap / hi:.1f}–{gap / max(lo, 1):.1f} h" if lo else "?"
        lines += ["", f"**Fastest method you can run now:** {best['name']} ({_n(lo)}–{_n(hi)}/h est., {hours} for the gap)", f"- {best['how']}", "",
                  "## Other options"]
        for m in avail[1:6]:
            lines.append(f"- {m['name']} — {_n(m['rate_per_hour_estimate'][0])}–{_n(m['rate_per_hour_estimate'][1])}/h · needs: {m['requires']}")
        blocked = [m for m in methods if not m["available_now"]]
        if blocked:
            lines += ["", "## Not yet available"]
            for m in blocked:
                lines.append(f"- {m['name']} — {'; '.join(m['blocked_by'])}")
    lines += ["", f"_Rates are community estimates checked {KNOWLEDGE_CHECKED}._"]
    return _fmt(data, params.response_format, "\n".join(lines))


class ExplainInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(..., min_length=1, max_length=60, description="e.g. 'nanites', 'upgrade modules', 'hyperdrive', 'portal glyphs', 'economy', 'S-class'")


@mcp.tool(name="nms_explain", annotations=ToolAnnotations(title="Explain a game mechanic", **READ_ONLY))
async def nms_explain(params: ExplainInput) -> str:
    """Short, dated explainer for a No Man's Sky mechanic (nanites, upgrade modules and classes, hyperdrive,
    portal glyphs, economy tiers, frigates, settlements, discoveries, quicksilver, save file timing)."""
    text = explain(params.topic)
    if text is None:
        return f"No explainer for '{params.topic}'. Available: {', '.join(topics())}."
    return f"**{params.topic.strip()}** — {text}\n\n_Checked {KNOWLEDGE_CHECKED}. Class reference: {'; '.join(UPGRADE_CLASSES[c].split(':')[0] for c in 'CBASX')}._"


class CommunityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(name="nms_get_community_mission", annotations=ToolAnnotations(title="Community mission progress", **READ_ONLY_NET))
async def nms_get_community_mission(params: CommunityInput) -> str:
    """Current community research mission progress (tier and percentage) from the public Assistant for
    No Man's Sky API. This is the only tool that uses the network; it sends nothing about your save."""
    try:
        data = await fetch_community_mission()
    except Exception as exc:  # noqa: BLE001 - network errors are reported, not raised
        return _err(f"community mission lookup failed ({type(exc).__name__}). Try again later.")
    md = f"# Community mission #{data['mission_id']} — tier {data['current_tier']}/{data['total_tiers']} at {data['percentage']}%"
    return _fmt(data, params.response_format, md)


from . import tools_more  # noqa: E402

tools_more.register(mcp, store, FormatInput, ResponseFormat, ToolAnnotations, READ_ONLY, _fmt, _err, _n, _snap, _ly)

from . import tools_shops  # noqa: E402

tools_shops.register(mcp, store, ResponseFormat, ToolAnnotations, _fmt, _err, _n, _snap, _ly)


# ----------------------------------------------------------------------------
# Resources
# ----------------------------------------------------------------------------


@mcp.resource("nms://player/state")
def player_state_resource() -> str:
    """Current player state as JSON (same as nms_get_player_state with response_format='json')."""
    try:
        return json.dumps(store.snapshot().summary(), indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _self_test(slot: int | None) -> int:
    """Load the newest save and print a short report. Exit 0 on success."""
    try:
        snap = store.snapshot(slot)
    except Exception as exc:  # noqa: BLE001
        print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
        return 1
    s = snap.summary()
    print(f"save: {snap.path} ({_age(snap)})")
    print(f"version {snap.version} · {snap.platform} · mapping libMBIN {snap.mapping.version if snap.mapping else '?'} · unknown keys {len(snap.unknown_keys)}")
    print(f"mode {snap.game_mode} · {s['play_time_hours']} h · units {snap.units:,} · nanites {snap.nanites:,} · quicksilver {snap.quicksilver:,}")
    print(f"location {snap.address}")
    print(f"inventories {len(snap.inventories())} · ships {len(snap.ships())} · multitools {len(snap.multitools())} · bases {len(snap.bases())} · teleporters {len(snap.teleporters())}")
    b = snap.discovery_backlog()
    print(f"discoveries {b['total_records']} · pending upload {b['pending_upload']} {b['pending_by_type']}")
    print(f"frigates {len(snap.frigates())} · expeditions {len(snap.fleet_expeditions())} · settlements {len(snap.settlements())} · missions in progress {len(snap.missions_in_progress())}")
    print("SELF-TEST OK")
    return 0


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="nms-direct-link", description="No Man's Sky Direct Link MCP server (read-only)")
    ap.add_argument("--version", action="version", version=f"nms-direct-link {__version__}")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5099)
    ap.add_argument("--slot", type=int, default=None, help="save slot to use (default: newest)")
    ap.add_argument("--list-saves", action="store_true", help="print save files and exit")
    ap.add_argument("--self-test", action="store_true", help="parse the newest save, print a summary, exit")
    ap.add_argument("--update-mapping", action="store_true", help="download the newest MBINCompiler mapping.json and exit")
    ap.add_argument("--prerelease", action="store_true", help="with --update-mapping: allow pre-release mappings")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.list_saves:
        saves = list_saves()
        if not saves:
            print("no saves found (set NMS_SAVE_DIR)", file=sys.stderr)
            sys.exit(1)
        for s in saves:
            print(f"{s.label:16} {s.platform:7} {s.modified:%Y-%m-%d %H:%M} UTC  {s.size // 1024:6} KiB  {s.path}")
        return
    if args.update_mapping:
        from .save.mapping import download_latest_mapping

        dest = download_latest_mapping(include_prerelease=args.prerelease)
        print(f"mapping saved to {dest}")
        return
    if args.self_test:
        sys.exit(_self_test(args.slot))
    if args.slot:
        import os

        os.environ["NMS_SAVE_SLOT"] = str(args.slot)
    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
