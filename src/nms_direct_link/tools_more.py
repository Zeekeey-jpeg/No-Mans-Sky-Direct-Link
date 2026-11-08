"""Galaxy, route, progress and companion tools (registered on the shared server in server.py)."""


import json

from pydantic import Field

from . import extras, history
from .galaxy import Atlas


def register(mcp, store, FormatInput, ResponseFormat, ToolAnnotations, READ_ONLY, _fmt, _err, _n, _snap, _ly):  # noqa: N803 - mirrors server names
    def atlas(slot: int | None) -> Atlas:
        return Atlas(_snap(slot))

    errors = (Exception,)

    # ---------------------------------------------------------------- galaxy / routes

    class SearchPlanetsInput(FormatInput):
        biome: str | None = Field(default=None, max_length=30, description="Lush, Toxic, Scorched, Radioactive, Frozen, Barren, Dead, Weird, Red, Green, Blue, Swamp, Lava, Waterworld, Gas Giant (aliases like 'paradise', 'ocean', 'volcanic' work)")
        infested: bool | None = Field(default=None, description="True = only infested planets, False = exclude them")
        named_only: bool = Field(default=False, description="Only planets you named")
        with_base: bool = Field(default=False, description="Only planets where you have a base")
        within_ly: float | None = Field(default=None, gt=0, description="Max distance in light-years")
        from_base: str | None = Field(default=None, max_length=60, description="Measure from this base or system instead of your position")
        discoverer: str | None = Field(default=None, max_length=60, description="System discoverer name (substring)")
        limit: int = Field(default=20, ge=1, le=200)

    @mcp.tool(name="nms_search_planets", annotations=ToolAnnotations(title="Search visited planets", **READ_ONLY))
    async def nms_search_planets(params: SearchPlanetsInput) -> str:
        """Search every planet recorded in your save by biome, infestation, name, base, discoverer and distance,
        nearest first. Each result includes portal glyphs and how much fauna, flora and minerals you catalogued there."""
        try:
            res = atlas(params.slot).search_planets(params.biome, params.infested, params.named_only, params.within_ly,
                                                    params.from_base, params.discoverer, params.with_base, params.limit)
        except errors as exc:
            return _err(str(exc))
        lines = [f"# Planets — {res['total']} match(es), nearest first from {res['origin']}", ""]
        for h in res["results"]:
            tags = ", ".join(t for t in [h["biome"] or "biome unknown", "infested" if h["infested"] else "", f"base: {', '.join(h['bases'])}" if h["bases"] else ""] if t)
            lines.append(f"- **{h['planet']}** in {h['system']} — {tags} · {_ly(h['distance_ly'])} · `{h['portal']}` · fauna {h['fauna_discovered']} / flora {h['flora_discovered']} / minerals {h['minerals_discovered']}")
        if res["has_more"]:
            lines.append(f"- … {res['total'] - res['count']} more (raise limit)")
        return _fmt(res, params.response_format, "\n".join(lines))

    class RouteInput(FormatInput):
        targets: list[str] = Field(default_factory=list, max_length=50, description="Systems or bases to visit: names, base names, portal glyphs, signal-booster codes")
        biome: str | None = Field(default=None, max_length=30, description="Also visit every known system with a planet of this biome")
        from_base: str | None = Field(default=None, max_length=60, description="Start from this base/system (default: your position)")
        warp_range: float | None = Field(default=None, gt=0, le=10000, description="Your hyperdrive range in ly; enables jump counts and hops through known systems")
        within_ly: float | None = Field(default=None, gt=0, description="Only biome targets within this radius")
        max_targets: int = Field(default=10, ge=1, le=50)
        algorithm: str = Field(default="2opt", pattern="^(2opt|nearest-neighbor)$")
        round_trip: bool = Field(default=False, description="Return to the start")

    @mcp.tool(name="nms_plan_route", annotations=ToolAnnotations(title="Plan a warp route", **READ_ONLY))
    async def nms_plan_route(params: RouteInput) -> str:
        """Plan a multi-stop warp route through systems in your save. Orders stops with nearest-neighbour + 2-opt,
        and with your warp range finds hop-by-hop paths through visited systems, counts jumps, and suggests a
        teleporter shortcut when one of your teleporters is closer to the first stop than you are."""
        if not params.targets and not params.biome:
            return _err("give targets (names, bases, glyphs) and/or a biome")
        try:
            r = atlas(params.slot).plan_route(params.targets, params.biome, params.from_base, params.warp_range,
                                              params.within_ly, params.max_targets, params.algorithm, params.round_trip)
        except errors as exc:
            return _err(str(exc))
        if not r["legs"]:
            return _fmt(r, params.response_format, f"No route: {r.get('note', 'no targets')}. Not found: {', '.join(r['missing']) or 'none'}.")
        lines = [f"# Route from {r['origin']} — {r['stops']} stop(s), {_ly(r['total_ly'])}"
                 + (f", {r['total_jumps']} jumps at {_n(r['warp_range_ly'])} ly range" if r["warp_range_ly"] else ""), ""]
        for i, leg in enumerate(r["legs"], 1):
            via = f" via {', '.join(leg['via_known_systems'])}" if leg.get("via_known_systems") else ""
            jumps = f" · {leg['jumps']} jump(s)" if "jumps" in leg else ""
            lines.append(f"{i}. {leg['from']} → **{leg['to']}** · {_ly(leg.get('path_ly', leg['straight_ly']))}{jumps}{via}")
        if r["teleport_shortcut"]:
            t = r["teleport_shortcut"]
            lines += ["", f"**Shortcut:** teleport to {t['teleport_to']} ({', '.join(t['teleporters'])}) first — saves {_ly(t['saves_ly'])}."]
        if r["missing"]:
            lines += ["", f"_Not in your save: {', '.join(r['missing'])}_"]
        return _fmt(r, params.response_format, "\n".join(lines))

    class SystemInput(FormatInput):
        query: str = Field(default="here", min_length=1, max_length=60, description="System name, base name, portal glyphs, booster code, packed address, or 'here'")

    @mcp.tool(name="nms_get_system", annotations=ToolAnnotations(title="System detail", **READ_ONLY))
    async def nms_get_system(params: SystemInput) -> str:
        """Everything your save knows about one star system: name, discoverer, every planet with biome, infestation
        and what you catalogued, your bases and teleporters there, pending uploads, coordinates and distance."""
        try:
            a = atlas(params.slot)
            s = a.find_system(params.query)
        except errors as exc:
            return _err(str(exc))
        if s is None:
            return _err(f"no system matching '{params.query}' in your save. Try nms_whats_nearby or nms_search_planets.")
        d = s.to_dict(a.here)
        lines = [f"# {s.label()} — {d['galaxy']}", "", f"- portal `{d['portal']}` · booster `{d['signal_booster']}` · {_ly(d['distance_ly'])} from you",
                 f"- discovered by {d['discoverer'] or '?'} · {d['discoveries']} records · {d['pending_upload']} waiting to upload"]
        if d["bases"]:
            lines.append(f"- bases: {', '.join(d['bases'])}")
        if d["teleporters"]:
            lines.append(f"- teleporters: {', '.join(d['teleporters'])}")
        lines += ["", "## Planets"]
        for p in d["planets"]:
            lines.append(f"- {p['name'] or 'planet ' + str(p['index'])}: {p['biome'] or 'biome unknown'}{' (infested)' if p['infested'] else ''} · fauna {p['fauna_discovered']} · flora {p['flora_discovered']} · minerals {p['minerals_discovered']}"
                         + (f" · base: {', '.join(p['bases'])}" if p["bases"] else ""))
        return _fmt(d, params.response_format, "\n".join(lines))

    class BaseInput(FormatInput):
        name: str = Field(..., min_length=1, max_length=60, description="Base name (case-insensitive, partial ok)")

    @mcp.tool(name="nms_get_base", annotations=ToolAnnotations(title="Base detail", **READ_ONLY))
    async def nms_get_base(params: BaseInput) -> str:
        """One of your bases: type, size in parts, last edit, glyphs, distance, and the system and planet it sits on."""
        try:
            snap = _snap(params.slot)
            a = Atlas(snap)
        except errors as exc:
            return _err(str(exc))
        q = params.name.lower()
        bases = [b for b in snap.bases() if q in str(b["name"]).lower()]
        if not bases:
            return _err(f"no base matching '{params.name}'. Your bases: {', '.join(b['name'] for b in snap.bases()) or 'none'}")
        b = bases[0]
        from .save.address import UniverseAddress
        addr = UniverseAddress.from_packed(b["address"]["packed"]) if b["address"] else None
        s = a.systems.get(addr.system_key()) if addr else None
        data = {**b, "distance_ly": round(a.here.distance_ly(addr)) if addr else None, "system": s.to_dict(a.here) if s else None}
        planet = s.planets.get(addr.planet) if (s and addr) else None
        md = "\n".join([f"# {b['name']} — {b['type']}", "",
                        f"- {b['objects']} parts · last updated {b['last_updated'] or '?'}",
                        f"- portal `{b['address']['portal'] if b['address'] else '?'}` · {_ly(data['distance_ly'])} from you",
                        f"- planet: {planet.biome if planet and planet.biome else 'biome unknown'}{' (infested)' if planet and planet.infested else ''} in {s.label() if s else '?'}"])
        return _fmt(data, params.response_format, md)

    class NearbyInput(FormatInput):
        count: int = Field(default=10, ge=1, le=100)
        biome: str | None = Field(default=None, max_length=30)
        from_base: str | None = Field(default=None, max_length=60)

    @mcp.tool(name="nms_whats_nearby", annotations=ToolAnnotations(title="What's nearby", **READ_ONLY))
    async def nms_whats_nearby(params: NearbyInput) -> str:
        """The nearest known systems to you (or to a base), optionally only those with a planet of a given biome,
        with planet biomes, bases, teleporters and pending uploads for each."""
        try:
            rows = atlas(params.slot).nearby(params.count, params.biome, params.from_base)
        except errors as exc:
            return _err(str(exc))
        lines = ["# Nearby systems", ""]
        for r in rows:
            biomes = ", ".join(sorted({p["biome"] for p in r["planets"] if p["biome"]})) or "no planet scans"
            extra = (" · bases: " + ", ".join(r["bases"])) if r["bases"] else ""
            lines.append(f"- {'📍 ' if r['here'] else ''}**{r['label']}** · {_ly(r['distance_ly'])} · {len(r['planets'])} planet(s): {biomes}{extra} · `{r['portal']}`")
        return _fmt({"systems": rows}, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_galaxy_stats", annotations=ToolAnnotations(title="Galaxy stats", **READ_ONLY))
    async def nms_get_galaxy_stats(params: FormatInput) -> str:
        """Your exploration footprint: systems and planets known, biome breakdown, infested and named counts,
        discoveries by type, bases, teleporters, galaxies visited, farthest system and closest approach to the centre."""
        try:
            s = atlas(params.slot).stats()
        except errors as exc:
            return _err(str(exc))
        lines = ["# Galaxy stats", "",
                 f"- **{s['systems']} systems**, **{s['planets']} planets** ({s['infested_planets']} infested, {s['named_planets']} named) · {s['bases']} bases · {s['teleporters']} teleporters",
                 f"- galaxies: {', '.join(s['galaxies_visited'])} · farthest system {_ly((s['farthest_system'] or {}).get('distance_ly'))} away · closest to centre {_ly(s['closest_to_centre_ly'])}",
                 "", "## Biomes"] + [f"- {k}: {v}" for k, v in s["biomes"].items()] + ["", "## Discoveries"] + [f"- {k}: {v}" for k, v in s["discoveries_by_type"].items()]
        return _fmt(s, params.response_format, "\n".join(lines))

    # ---------------------------------------------------------------- progress / player

    @mcp.tool(name="nms_get_player_stats", annotations=ToolAnnotations(title="Lifetime stats", **READ_ONLY))
    async def nms_get_player_stats(params: FormatInput) -> str:
        """Lifetime career stats the game tracks: warps, aliens met, deaths, upgrades, creatures discovered, units
        earned from scanning, sessions, distance walked on hot/cold worlds, black hole warps and more."""
        try:
            d = extras.player_stats(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = [f"# Career stats — {d['play_time_hours']} h played", ""] + [f"- {v['label']}: {_n(v['value'])}" for v in d["stats"].values()]
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_standing", annotations=ToolAnnotations(title="Reputation and language", **READ_ONLY))
    async def nms_get_standing(params: FormatInput) -> str:
        """Reputation with the Gek, Vy'keen, Korvax and Autophage, guild standings, and how many words you know in
        each alien language. Higher standing means bigger station discounts and more dialogue options."""
        try:
            d = extras.standing(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = ["# Standing", ""] + [f"- {k}: {v}" for k, v in d["standing"].items()] + ["", "## Words known"] + [f"- {k}: {v}" for k, v in d["words_known"].items()]
        return _fmt(d, params.response_format, "\n".join(lines) + f"\n\n_{d['note']}_")

    @mcp.tool(name="nms_get_trade_log", annotations=ToolAnnotations(title="Trade log by system", **READ_ONLY))
    async def nms_get_trade_log(params: FormatInput) -> str:
        """Where you have traded: per system, the goods you bought or sold, which markets you saturated (sold so much
        the price dropped) and how many play-hours ago. Use it to avoid crashed prices and plan trade runs."""
        try:
            d = extras.trade_log(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = [f"# Trade log — {len(d['systems'])} system(s)", ""]
        for s in d["systems"]:
            sat = f" · ⚠ saturated: {', '.join(s['saturated'])}" if s["saturated"] else ""
            lines.append(f"- **{s['system']}** · {_ly(s['distance_ly'])} · {s['products_traded']} goods{sat}")
        return _fmt(d, params.response_format, "\n".join(lines) + f"\n\n_{d['note']}_")

    @mcp.tool(name="nms_get_records", annotations=ToolAnnotations(title="Wonder records", **READ_ONLY))
    async def nms_get_records(params: FormatInput) -> str:
        """Your Wonders catalogue: largest and smallest creatures, hottest, coldest, most toxic and largest planets,
        extreme flora, minerals and treasures you have scanned, with where they are."""
        try:
            d = extras.wonder_records(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = ["# Wonder records", ""]
        for kind, rows in d["records"].items():
            lines.append(f"## {kind.title()}")
            for r in rows:
                lines.append(f"- {r['record']}: {r['value']} · `{r['where'] or '?'}` · {_ly(r['distance_ly'])}")
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_companions", annotations=ToolAnnotations(title="Companions and eggs", **READ_ONLY))
    async def nms_get_companions(params: FormatInput) -> str:
        """Your creature companions (species, biome, size, predator, adoption date), eggs, Xeno Arena battle team
        and how many companion slots you have unlocked."""
        try:
            d = extras.companions(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = [f"# Companions — {len(d['companions'])} adopted, {d['unlocked_slots']}/{d['max_slots']} slots unlocked, {d['eggs']} egg(s)", ""]
        for c in d["companions"]:
            lines.append(f"- slot {c['slot']}: **{c['name'] or c['species']}** · {c['biome']} · scale {c['scale']}{' · predator' if c['predator'] else ''}")
        if not d["companions"]:
            lines.append("- none yet. Feed a creature its favourite bait and use the Adopt option to tame it.")
        lines.append(f"\nBattle team: {', '.join('slot ' + str(i) for i in d['battle_team_slots']) or 'not set'}")
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_hangar", annotations=ToolAnnotations(title="Ships, corvettes and crew", **READ_ONLY))
    async def nms_get_hangar(params: FormatInput) -> str:
        """Every starship and corvette you own (archetype, class, stats, upgrades), free ship slots, multitools,
        corvette storage, squadron pilots, hired base workers and fleet size."""
        try:
            d = extras.hangar(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = [f"# Hangar — {d['ship_slots_used']}/{d['ship_slots']} ship slots, {len(d['corvettes'])} corvette(s)", ""]
        for s in d["ships"]:
            lines.append(f"- **{s['name']}** — {s['class']}-class {s['archetype']}{' (primary)' if s['primary'] else ''} · stats {s['base_stats']} · upgrades: {', '.join(s['upgrades']) or 'none'}")
        lines += ["", f"Multitools: {len(d['multitools'])}/{d['multitool_slots']} · Squadron: {len(d['squadron_pilots'])} pilot(s), {d['squadron_slots_unlocked']} slot(s) unlocked · "
                  f"Workers hired: {d['hired_workers']} · Frigates: {d['frigates']} · Corvette storage items: {d['corvette_storage_items']}"
                  + (" · corvette design in progress" if d["corvette_draft_in_progress"] else "")]
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_waypoints", annotations=ToolAnnotations(title="Waypoints, markers and grave", **READ_ONLY))
    async def nms_get_waypoints(params: FormatInput) -> str:
        """Active galaxy-map waypoints, mission markers (with building type and distance), your item grave and what
        is in it, and recently visited systems."""
        try:
            d = extras.waypoints(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = ["# Waypoints", ""]
        for w in d["galaxy_waypoints"]:
            lines.append(f"- 🧭 {w['type']} `{w['event']}` · `{w['portal']}` · {_ly(w['distance_ly'])}")
        for m in d["mission_markers"]:
            lines.append(f"- 🎯 `{m['mission']}` → {m['building'] or 'marker'} on planet {m['planet_index']} · `{m['portal']}` · {_ly(m['distance_ly'])}")
        if d["grave"]:
            g = d["grave"]
            lines.append(f"- 💀 Grave {'in space' if g['in_space'] else 'on planet ' + str(g['planet_index'])} · `{g['portal']}` · {_ly(g['distance_ly'])} · {', '.join(g['items'][:8])}")
        lines.append(f"\nVisited systems recorded: {d['visited_systems_count']}")
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_timers", annotations=ToolAnnotations(title="What's ready", **READ_ONLY))
    async def nms_get_timers(params: FormatInput) -> str:
        """One dashboard of everything time-based: frigate expeditions, daily/weekly mission resets, settlement
        judgements, an item grave to recover, and discoveries waiting to upload. Ready items first."""
        try:
            d = extras.timers(_snap(params.slot))
        except errors as exc:
            return _err(str(exc))
        lines = [f"# What's ready — {d['ready_now']} now", ""]
        for i in d["items"]:
            when = "✅ ready" if i["ready"] else f"⏳ {i['seconds_left'] // 3600}h {(i['seconds_left'] % 3600) // 60}m"
            lines.append(f"- {when} · **{i['what']}** — {i['action']}")
        return _fmt(d, params.response_format, "\n".join(lines))

    class ChangesInput(FormatInput):
        compare_to: str = Field(default="last", pattern="^(last|first|autosave)$",
                                description="'last' = previous recorded session, 'first' = earliest recorded, 'autosave' = the other file in the same slot")

    @mcp.tool(name="nms_get_session_changes", annotations=ToolAnnotations(title="What changed", **READ_ONLY))
    async def nms_get_session_changes(params: ChangesInput) -> str:
        """What changed between your current save and a previous one: units, nanites and quicksilver earned or spent,
        new discoveries and systems, items gained or used, tech installed or removed, and where you moved.
        History is a small file in your user cache folder (never the game folder); disable with NMS_NO_HISTORY=1."""
        try:
            snap = _snap(params.slot)
            new = history.summarise(snap)
            if params.compare_to == "autosave":
                from .save import list_saves, load_snapshot
                cur = snap.path
                others = [s for s in list_saves() if s.path != cur and s.account == (cur.parent.name if cur else None)]
                pair = [s for s in others if snap.path and s.slot == next((x.slot for x in list_saves() if x.path == cur), None)]
                if not pair:
                    return _err("no other save in this slot to compare with")
                old = history.summarise(load_snapshot(pair[0].path, store.mapping))
            else:
                rows = [r for r in history.read_history(new["save_account"]) if r.get("save_modified") != new["save_modified"]]
                if not rows:
                    return _fmt({"history": 0}, params.response_format,
                                "No earlier session recorded yet. History starts the first time the server loads a save; ask again after your next save.")
                old = rows[0] if params.compare_to == "first" else rows[-1]
        except errors as exc:
            return _err(str(exc))
        d = history.diff(old, new)
        lines = [f"# Changes since {d['from']} ({d['played_minutes']} min played)", ""]
        for k, v in d["changes"].items():
            lines.append(f"- {k.replace('_', ' ')}: {_n(v['before'])} → {_n(v['after'])} ({'+' if v['change'] > 0 else ''}{_n(v['change'])})")
        if d["moved"]:
            lines.append(f"- moved from `{d['from_location']}` to `{d['to_location']}`")
        if d["tech_added"]:
            lines.append(f"- tech added: {', '.join(d['tech_added'])}")
        if d["tech_removed"]:
            lines.append(f"- tech removed: {', '.join(d['tech_removed'])}")
        if d["items_changed"]:
            lines += ["", "## Items"] + [f"- {k}: {'+' if v > 0 else ''}{_n(v)}" for k, v in d["items_changed"].items()]
        if len(lines) == 2:
            lines.append("- nothing changed")
        return _fmt(d, params.response_format, "\n".join(lines))

    @mcp.tool(name="nms_get_progress_history", annotations=ToolAnnotations(title="Progress over time", **READ_ONLY))
    async def nms_get_progress_history(params: FormatInput) -> str:
        """Your recorded sessions over time: units, nanites, quicksilver, discoveries and systems at each save the
        server has seen, oldest first. Good for 'how fast am I earning nanites'."""
        try:
            snap = _snap(params.slot)
            rows = history.read_history(snap.path.parent.name if snap.path else None)
        except errors as exc:
            return _err(str(exc))
        slim = [{k: r.get(k) for k in ("save_modified", "play_seconds", "units", "nanites", "quicksilver", "discoveries", "systems_known")} for r in rows]
        if not slim:
            return _fmt({"sessions": []}, params.response_format, "No sessions recorded yet; history begins with the next save the server loads.")
        lines = [f"# Progress — {len(slim)} recorded save(s)", "", "| saved | hours | units | nanites | quicksilver | discoveries | systems |", "|---|---|---|---|---|---|---|"]
        for r in slim[-30:]:
            lines.append(f"| {str(r['save_modified'])[:16]} | {round((r['play_seconds'] or 0) / 3600, 1)} | {_n(r['units'])} | {_n(r['nanites'])} | {_n(r['quicksilver'])} | {_n(r['discoveries'])} | {_n(r['systems_known'])} |")
        return _fmt({"sessions": slim}, params.response_format, "\n".join(lines))

    # ---------------------------------------------------------------- resources

    @mcp.resource("nms://galaxy/stats")
    def galaxy_stats_resource() -> str:
        """Exploration footprint as JSON (same as nms_get_galaxy_stats)."""
        try:
            return json.dumps(Atlas(store.snapshot()).stats(), indent=2, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @mcp.resource("nms://bases")
    def bases_resource() -> str:
        """Your bases as JSON."""
        try:
            return json.dumps(store.snapshot().bases(), indent=2, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

