# Changelog

All notable changes to No Man's Sky Direct Link are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

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
