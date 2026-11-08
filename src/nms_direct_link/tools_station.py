"""Cockpit tools: station brief, upgrade plan, best prices."""

from pydantic import BaseModel, ConfigDict, Field

from . import planner


def register(mcp, ResponseFormat, ToolAnnotations, READ_ONLY, _fmt, _err, _n, _snap, _ly):  # noqa: N803
    class FmtOnly(BaseModel):
        model_config = ConfigDict(extra="forbid")
        response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @mcp.tool(name="nms_station_brief", annotations=ToolAnnotations(title="Station brief from the cockpit", **READ_ONLY))
    async def nms_station_brief(params: FmtOnly) -> str:
        """Dock, stay in your ship, ask "what's at this station for me?". Combines your wallet, every shop you have
        scanned here before, the upgrades you're missing or running low-class on, and goods you've already crashed
        the price of here, then says which merchant to open first. It cannot see unscanned stock (the game does not
        save it); open that merchant and use nms_look_at_screen to scan it."""
        try:
            b = planner.station_brief(_snap(None))
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        w = b["wallet"]
        lines = [f"# Station brief — `{b['system']}`", "",
                 f"**Wallet:** {_n(w['units'])} units · {_n(w['nanites'])} nanites · {_n(w['quicksilver'])} quicksilver",
                 f"**Open first:** the {b['open_first']}", ""]
        if b["look_for"]:
            lines.append("## Look for")
            for s in b["look_for"]:
                have = ", ".join(s["installed"]) or "none"
                lines.append(f"- **{s['upgrade']}** ({s['group']}) · have {have} · {s['action']} · ~{_n(s['estimated_nanites'])} nanites each, {s['modules_needed']} needed{' · ✅ can afford ' + str(s['affordable_count']) if s['affordable_now'] else ''}")
        if b["scanned_shops_here"]:
            lines += ["", "## Scanned here before"]
            for v in b["scanned_shops_here"]:
                items = ", ".join(f"{i['item_class'] + '-' if i['item_class'] else ''}{i['name']}" for i in v["items"][:8])
                lines.append(f"- {v['merchant'].title()} ({v['seen_hours_ago']} h ago): {items}")
        else:
            lines += ["", "_No shops scanned at this station yet._"]
        if b["trade_here"] and b["trade_here"]["saturated"]:
            lines += ["", f"⚠ Don't sell here again yet: {', '.join(b['trade_here']['saturated'])} (you already pushed the price down)."]
        lines += ["", "## Merchants at a space station"] + [f"- {'✓ ' if m['scanned_here'] else ''}{m['merchant'].title()}: {m['sells']}" for m in b["merchants"]]
        lines += ["", f"_{b['note']}_"]
        return _fmt(b, params.response_format, "\n".join(lines))

    class PlanInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        budget_nanites: int | None = Field(default=None, ge=0, le=100_000_000, description="Plan against this budget instead of your balance")
        response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @mcp.tool(name="nms_upgrade_plan", annotations=ToolAnnotations(title="Upgrade plan", **READ_ONLY))
    async def nms_upgrade_plan(params: PlanInput) -> str:
        """What to upgrade next: for your hyperdrive, shields, weapons, jetpack, life support, hazard protection, mining
        beam, scanner and more, shows installed module classes, free upgrade slots (max 3 per type), what to replace,
        rough nanite cost, what you can afford, and the best match you've seen in a scanned shop."""
        try:
            p = planner.upgrade_plan(_snap(None), params.budget_nanites)
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        lines = [f"# Upgrade plan — {_n(p['nanites'])} nanites, ~{_n(p['planned_spend'])} affordable now", ""]
        for s in p["steps"]:
            seen = s["best_seen"]
            where = f" · seen: {seen['item_class'] or '?'}-class for {_n(seen['price'])} {seen['currency'] or ''} at `{seen['portal']}` ({_ly(seen['distance_ly'])})" if seen else ""
            lines.append(f"- {'✅' if s['affordable_now'] else '⏳'} **{s['upgrade']}** ({s['group']}) · have {', '.join(s['installed']) or 'none'} · {s['action']}{where}")
        if p["complete_families"]:
            lines += ["", f"Maxed: {', '.join(p['complete_families'])}"]
        lines += ["", f"_{p['note']}_"]
        return _fmt(p, params.response_format, "\n".join(lines))

    class PricesInput(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        query: str | None = Field(default=None, max_length=60, description="Item name fragment, e.g. 'warp cell'")
        item_class: str | None = Field(default=None, max_length=2)
        limit: int = Field(default=25, ge=1, le=200)
        response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @mcp.tool(name="nms_best_prices", annotations=ToolAnnotations(title="Best prices seen", **READ_ONLY))
    async def nms_best_prices(params: PricesInput) -> str:
        """Price memory across every shop you've scanned: cheapest and highest price seen for each item, how many
        times you've seen it, and where the cheapest one was. "Is this a good price?" and "where's the cheapest X?"."""
        try:
            rows = planner.best_prices(_snap(None).address, params.query, params.item_class, params.limit)
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        if not rows:
            return _fmt({"items": []}, params.response_format, "No priced items in your scanned shops yet.")
        lines = ["# Best prices seen", "", "| item | cheapest | highest | seen | where |", "|---|---|---|---|---|"]
        for r in rows:
            cls = f"{r['item_class']}-class " if r["item_class"] else ""
            lines.append(f"| {cls}{r['name']} | {_n(r['cheapest'])} {r['currency'] or ''} | {_n(r['highest'])} | {r['times_seen']}× | {r['merchant']} `{r['where']}` ({_ly(r['distance_ly'])}) |")
        return _fmt({"items": rows}, params.response_format, "\n".join(lines))
