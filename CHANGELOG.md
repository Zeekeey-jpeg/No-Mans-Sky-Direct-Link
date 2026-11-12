# Changelog

All notable changes to No Man's Sky Direct Link are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added
- Personalized [M8ven](https://m8ven.ai/mcp/zeekeey-jpeg-no-mans-sky-direct-link-1emc87?s=readme) verification badge in the README (valid until 30 Nov 2026).
- A registry test that every one of the 37 tools advertises all four MCP tool hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) as explicit booleans.

### Changed
- Shop Scanner tools now share the same read-only hint set as the save readers (`idempotentHint` is true). `nms_log_shop` stays a local write: `readOnlyHint` false, `destructiveHint` true (re-logging a merchant replaces the earlier list), `idempotentHint` false, `openWorldHint` false. `nms_get_community_mission` remains the only tool with `openWorldHint` true.

## [0.3.0] — 2026-11-08

Built around docking and staying in the cockpit. 37 tools, 3 resources.

### Added
- `nms_station_brief`: dock and ask "what's at this station for me?" Wallet, shops scanned here before, upgrades you need, goods you've already saturated here, and which merchant to open first.
- `nms_upgrade_plan`: per technology (hyperdrive, shields, weapons, jetpack, life support, hazard, mining beam, scanner, freighter hyperdrive…) installed module classes, free slots (max 3), what to replace, nanite estimate, affordability, and the best match seen in scanned shops.
- `nms_best_prices`: price memory across every scanned shop: cheapest, highest, times seen, where.
- Command-line bridge: `--list-tools` and `--call TOOL --args JSON`, so assistants that run commands (Grok desktop, ChatGPT desktop, scripts) can use every tool without MCP.

### Fixed
- Trade log groups markets per system (it was splitting one market by planet).

## [0.2.0] — 2026-11-08

Full parity with existing No Man's Sky MCP tooling, the Shop Scanner, then everything else the save holds. 34 tools, 3 resources.

### Added
- **Shop Scanner**: `nms_look_at_screen` (game-window screenshot for the assistant to read), `nms_read_screenshots` (Steam F12 shots), `nms_log_shop`, `nms_find_in_shops`, `nms_get_shops_here`. Local SQLite store; `Pillow` dependency.
- Galaxy atlas from discovery records with planet **biomes** and infestation decoded, custom names, fauna/flora/mineral counts per planet.
- `nms_search_planets`, `nms_whats_nearby`, `nms_get_system`, `nms_get_base`, `nms_get_galaxy_stats`.
- `nms_plan_route`: nearest-neighbour + 2-opt ordering, warp-range jump counts, Dijkstra hops through known systems, teleporter shortcut suggestions, round trips.
- `nms_get_hangar` (ships, corvettes, squadron, workers), `nms_get_companions` (pets, eggs, arena team), `nms_get_player_stats`, `nms_get_standing` (race and guild reputation, words per language), `nms_get_trade_log` (crashed markets), `nms_get_records` (Wonders), `nms_get_waypoints` (mission markers, item grave), `nms_get_timers` (what's ready).
- Session history (`history.jsonl` in the user cache, opt-out `NMS_NO_HISTORY=1`) with `nms_get_session_changes` and `nms_get_progress_history`.
- Resources `nms://galaxy/stats` and `nms://bases`.
- README before-and-after comparison chart.

### Changed
- Distances between different stars in one region show as "same region" instead of 0 ly.

## [0.1.0] — 2026-11-08

First public release. Read-only, offline, save-file based.

### Added
- Save discovery for Steam and GOG on Windows, macOS and Linux (Proton), plus `NMS_SAVE_DIR` / `NMS_SAVE_FILE` / `NMS_SAVE_SLOT` overrides.
- LZ4 block decoder for `save*.hg` and key de-obfuscation with the MBINCompiler mapping (libMBIN 7.10.0.1 vendored; `--update-mapping` fetches newer).
- Galactic address math: voxel ↔ portal glyphs ↔ signal booster ↔ packed u64, distances, galaxy names.
- Typed save model: currencies, location, every inventory (exosuit, ships, multitools, freighter, exocraft, storage), upgrade module classes, discoveries and upload backlog, bases, teleporters, missions, recurring deadlines, frigates and fleet expeditions, settlements, known tech.
- 13 MCP tools (`nms_*`), all read-only, markdown or JSON output: list saves, player state, location, convert coordinates, tech audit, find item, discovery backlog, fleet status, settlements, missions, nanite plan, explain, community mission.
- `nms://player/state` resource.
- CLI: `--list-saves`, `--self-test`, `--update-mapping`, stdio (default) or streamable-http transport.
- Curated, dated knowledge base for nanite methods, upgrade classes and core mechanics.
- Test suite on a fully synthetic save fixture; optional real-save smoke test gated by `NMS_SMOKE_SAVE`.

### Known limits
- Station merchant stock, module stat rolls, planet biomes/resources of unvisited planets: not in the save, not predicted (see README roadmap).
- Xbox / Game Pass (WGS container) saves not supported yet.
- Item display names are a partial curated list; unknown IDs are shown humanised.
