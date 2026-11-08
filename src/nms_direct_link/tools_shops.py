"""Shop Scanner MCP tools: look at the merchant screen, remember it, search it later."""

from mcp.server.mcpserver import Image
from pydantic import BaseModel, ConfigDict, Field

from . import shops

READ_HINT = (
    "Read every item on the merchant screen: name, class letter (C/B/A/S/X) if shown, price and currency "
    "(units, nanites, quicksilver, or a trade item), and category. Then call nms_log_shop with what you read so it "
    "can be searched later. If no shop is open, tell the player to open the merchant screen and ask again."
)


def register(mcp, store, ResponseFormat, ToolAnnotations, _fmt, _err, _n, _snap, _ly):  # noqa: N803
    read_only = {"read_only_hint": True, "destructive_hint": False, "idempotent_hint": False, "open_world_hint": False}
    writes_local = {"read_only_hint": False, "destructive_hint": True, "idempotent_hint": False, "open_world_hint": False}

    class LookInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        target: str = Field(default="game", pattern="^(game|screen)$", description="'game' = the No Man's Sky window, 'screen' = everything")
        max_width: int = Field(default=1600, ge=640, le=3840, description="Downscale to this width (smaller = fewer tokens)")

    @mcp.tool(name="nms_look_at_screen", annotations=ToolAnnotations(title="Look at the game screen", **read_only))
    async def nms_look_at_screen(params: LookInput) -> list:
        """Shop Scanner, step 1: take a screenshot of the No Man's Sky window right now and return it so you can read it.
        Only the game window is captured; if it is not found nothing is captured unless target='screen' is passed.
        Use when the player says "what's in this shop?", "what can I buy here?", "read this screen". Works while
        docked with a merchant, trade terminal, outfitter or mission board open. Run the game in borderless or
        windowed mode (exclusive fullscreen can capture black). Nothing touches the game process."""
        try:
            shot = shops.capture_game_window(params.target, params.max_width)
        except Exception as exc:  # noqa: BLE001
            return [f"Error: {exc}. Try target='screen', or press F12 in game and use nms_read_screenshots."]
        where = ""
        try:
            snap = _snap(None)
            where = f" Player is in {snap.address} per the save written {snap.modified:%H:%M} UTC."
        except Exception:  # noqa: BLE001
            pass
        text = f"Captured {shot.source} ({shot.width}x{shot.height}).{where} {READ_HINT}"
        return [text, Image(data=shot.data, format="jpeg")]

    class ScreenshotsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        limit: int = Field(default=4, ge=1, le=12, description="How many of the newest screenshots")
        within_minutes: float = Field(default=120, gt=0, le=100000, description="Only screenshots taken in this window")
        max_width: int = Field(default=1400, ge=640, le=3840)

    @mcp.tool(name="nms_read_screenshots", annotations=ToolAnnotations(title="Read my F12 screenshots", **read_only))
    async def nms_read_screenshots(params: ScreenshotsInput) -> list:
        """Shop Scanner without alt-tabbing: press Steam's F12 at each shop while you play, then ask once.
        Returns your newest No Man's Sky Steam screenshots (or NMS_SCREENSHOT_DIR) as images to read and log."""
        try:
            shots = shops.recent_steam_screenshots(params.limit, params.within_minutes, params.max_width)
        except Exception as exc:  # noqa: BLE001
            return [f"Error: {exc}"]
        if not shots:
            dirs = shops.steam_screenshot_dirs()
            return ["No recent No Man's Sky screenshots found. Press F12 in game (Steam overlay) at the shop screen, then ask again."
                    + ("" if dirs else " No Steam screenshot folder exists yet for the game; it appears after your first F12, or set NMS_SCREENSHOT_DIR.")]
        out: list = [f"{len(shots)} screenshot(s), newest first. Each was taken where the player was at that time; if they warped since, "
                     f"pass station/portal context to nms_log_shop. {READ_HINT}"]
        for s in shots:
            out.append(f"— {s.source}")
            out.append(Image(data=s.data, format="jpeg"))
        return out

    class ShopItem(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        name: str = Field(..., min_length=1, max_length=120)
        item_class: str | None = Field(default=None, max_length=2, description="C, B, A, S or X for upgrades/ships/tools")
        category: str | None = Field(default=None, max_length=60, description="e.g. 'hyperdrive upgrade', 'trade good', 'blueprint'")
        price: float | None = Field(default=None, ge=0)
        currency: str | None = Field(default=None, max_length=30, description="units, nanites, quicksilver, or the item traded")
        quantity: int | None = Field(default=None, ge=0)
        detail: str | None = Field(default=None, max_length=300, description="stats shown on hover, if visible")

    class LogShopInput(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        merchant: str = Field(..., min_length=2, max_length=40, description=f"One of: {', '.join(shops.MERCHANTS)}")
        items: list[ShopItem] = Field(..., min_length=1, max_length=200)
        station: str | None = Field(default=None, max_length=80, description="Station or outpost name if visible")
        economy: str | None = Field(default=None, max_length=60, description="Economy/wealth if visible (e.g. 'Wealthy · Technology')")
        note: str | None = Field(default=None, max_length=300)
        portal: str | None = Field(default=None, max_length=16, description="Only if the shop is NOT in the player's current system (12 glyphs)")

    @mcp.tool(name="nms_log_shop", annotations=ToolAnnotations(title="Remember a shop", **writes_local))
    async def nms_log_shop(params: LogShopInput) -> str:
        """Shop Scanner, step 2: remember what a merchant sells, tied to the player's current system from the save
        (or a given portal). Re-logging the same merchant in the same system replaces the old list.
        Stored in a local SQLite file in the user cache folder."""
        try:
            if params.portal:
                from .save.address import UniverseAddress

                addr = UniverseAddress.from_portal(params.portal, _snap(None).address.galaxy)
            else:
                addr = _snap(None).address
            res = shops.log_shop(addr, params.merchant.lower(), [i.model_dump() for i in params.items],
                                 params.station, params.economy, params.note)
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        return (f"Logged {res['items']} item(s) from the {res['merchant']} at `{res['portal']}`"
                + (" (replaced the earlier list)" if res["replaced_previous"] else "") + ". Ask nms_find_in_shops later to search every shop you've scanned.")

    class FindInput(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        query: str | None = Field(default=None, max_length=60, description="Item name or category fragment, e.g. 'hyperdrive', 'warp cell'")
        item_class: str | None = Field(default=None, max_length=2, description="C, B, A, S or X")
        max_price: float | None = Field(default=None, ge=0)
        currency: str | None = Field(default=None, max_length=30)
        merchant: str | None = Field(default=None, max_length=40)
        limit: int = Field(default=25, ge=1, le=200)
        response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @mcp.tool(name="nms_find_in_shops", annotations=ToolAnnotations(title="Search scanned shops", **read_only))
    async def nms_find_in_shops(params: FindInput) -> str:
        """Search every shop you have scanned: "where did I see an S-class hyperdrive module under 600 nanites?".
        Results are nearest first, with glyphs, merchant, price and how long ago you saw it."""
        try:
            here = _snap(None).address
            rows = shops.find_items(here, params.query, params.item_class, params.max_price, params.currency, params.merchant, params.limit)
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        if not rows:
            s = shops.summary()
            return _fmt({"results": [], **s}, params.response_format,
                        f"No match in {s['visits']} scanned shop(s). Dock, open a merchant and ask \"what's in this shop?\" to add more.")
        lines = [f"# Shop matches — {len(rows)}", ""]
        for r in rows:
            price = f"{_n(r['price'])} {r['currency'] or ''}".strip() if r["price"] is not None else "price ?"
            cls = f"{r['item_class']}-class " if r["item_class"] else ""
            lines.append(f"- **{cls}{r['name']}** · {price} · {r['merchant']}{' at ' + r['station'] if r['station'] else ''} · `{r['portal']}` · {_ly(r['distance_ly'])} · seen {r['seen_hours_ago']} h ago")
        return _fmt({"results": rows}, params.response_format, "\n".join(lines))

    class ShopsHereInput(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        portal: str | None = Field(default=None, max_length=16, description="12 glyphs; default = where you are now")
        response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @mcp.tool(name="nms_get_shops_here", annotations=ToolAnnotations(title="Shops scanned in a system", **read_only))
    async def nms_get_shops_here(params: ShopsHereInput) -> str:
        """Quick view of every shop you have scanned in this system (or a given portal address): merchant by
        merchant, what they sold and for how much, and how long ago you looked."""
        try:
            if params.portal:
                from .save.address import UniverseAddress

                addr = UniverseAddress.from_portal(params.portal, _snap(None).address.galaxy)
            else:
                addr = _snap(None).address
            visits = shops.shops_at(addr)
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc))
        if not visits:
            return _fmt({"shops": []}, params.response_format,
                        "No shops scanned in this system yet. Open a merchant screen and ask \"what's in this shop?\".")
        lines = [f"# Shops in `{addr.portal()}` — {len(visits)} scanned", ""]
        for v in visits:
            lines.append(f"## {v['merchant'].title()}{' · ' + v['station'] if v['station'] else ''} (seen {v['seen_hours_ago']} h ago)")
            for i in v["items"]:
                price = f"{_n(i['price'])} {i['currency'] or ''}".strip() if i["price"] is not None else ""
                lines.append(f"- {i['item_class'] + '-class ' if i['item_class'] else ''}{i['name']}{' · ' + price if price else ''}")
        return _fmt({"shops": visits}, params.response_format, "\n".join(lines))

