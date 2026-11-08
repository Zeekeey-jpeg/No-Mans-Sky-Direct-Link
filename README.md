<p align="center">
  <img src="docs/banner.svg" alt="No Man's Sky Direct Link" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-13%20tools%20%2B%20resource-5b1e6b">
  <img alt="Read-only" src="https://img.shields.io/badge/save%20file-read--only-2ea44f">
  <img alt="Game version" src="https://img.shields.io/badge/NMS-7.13%20Forsaken-e2592b">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
</p>

# No Man's Sky Direct Link — MCP server for No Man's Sky

<h3 align="center">Give your AI assistant full visibility into your No Man's Sky game.</h3>
<p align="center">A local <a href="https://modelcontextprotocol.io">Model Context Protocol</a> (MCP) server for <strong>No Man's Sky</strong> that reads <em>your own</em> save file and answers questions like<br>
<em>"How many nanites do I have and what's the fastest way to 3,000?" · "Where did I leave my Chromatic Metal?" · "Is anything on my ship damaged?" · "What are the glyphs for my base?"</em></p>

---

## ◆ TL;DR

- **What it is:** an MCP server (`nms-direct-link`) that decodes `save.hg`, de-obfuscates it with the community key mapping, and exposes **13 read-only tools** to Claude Desktop, Claude Code, or any MCP client.
- **What it never does:** write to your save, touch the game process, read memory, intercept network traffic, or send your data anywhere. The only network call is an optional public community-mission lookup.
- **Install:** `pipx install git+https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link` then add one JSON block to your MCP client. Saves are found automatically (Steam, GOG).
- **Check it works:** `nms-direct-link --self-test`

```
save: C:\Users\you\AppData\Roaming\HelloGames\NMS\st_7656…\save.hg (12 min ago)
version 4745 · Win|Final · mapping libMBIN 7.10.0.1 · unknown keys 0
mode Normal · 41.2 h · units 12,480,300 · nanites 1,930 · quicksilver 450
location Euclid 0863:007C:060B:01AB planet 1 (portal 11AB7E60D865)
inventories 19 · ships 3 · multitools 2 · bases 4 · teleporters 15
discoveries 512 · pending upload 143 {'Mineral': 61, 'Flora': 39, 'Animal': 28, 'Planet': 9, 'SolarSystem': 6}
frigates 7 · expeditions 1 · settlements 1 · missions in progress 24
SELF-TEST OK
```

---

## ◆ Features

| Tool | What your assistant can answer |
|---|---|
| `nms_get_player_state` | Units, nanites, quicksilver, mode, play time, where you are (glyphs, booster code, distance to centre), health, Nexus access, current mission, how old the save is |
| `nms_get_location` | Current / previous / freighter systems in every coordinate form, plus your bases and the whole teleporter network with distances |
| `nms_convert_coordinates` | Portal glyphs ↔ signal booster ↔ voxel ↔ packed address, with distance from you |
| `nms_audit_tech` | Every installed technology and upgrade module with its **C/B/A/S/X class**, damaged or uninstalled tech, free slots, ship and multitool class and stats |
| `nms_find_item` | "Where is my X?" across exosuit, ships, multitools, freighter, exocraft, all storage containers, cooking and grave inventories |
| `nms_get_discovery_backlog` | How many of **your** discoveries are still waiting to be uploaded for nanites, by type and by system |
| `nms_get_fleet_status` | Freighter class and tech, every frigate's role/class/record, fleet expeditions in progress with ETA |
| `nms_get_settlements` | Population, pending judgements, buildings under construction |
| `nms_get_missions` | Current mission, missions with recorded progress, daily/weekly/community deadlines |
| `nms_plan_nanites` | A plan to reach a nanite target: free nanites first (pending uploads), then the fastest farming methods you can actually run given your units and progress |
| `nms_explain` | Short, dated explainers: nanites, upgrade classes, hyperdrive and coloured stars, portal glyphs, economy tiers, frigates, settlements, quicksilver, save timing |
| `nms_list_saves` | Every save slot found, newest first, with platform and timestamp |
| `nms_get_community_mission` | Current community research progress (public Assistant for No Man's Sky API) |

Every tool takes `response_format: "markdown" | "json"` and an optional `slot`. A `nms://player/state` resource mirrors the player state as JSON.

**Freshness.** The game writes the save at save points, when you exit your ship and on a periodic autosave. The server reloads automatically when the file changes, so answers lag live play by seconds to a few minutes.

---

## ◆ Install

Requires Python 3.11+ and No Man's Sky on PC (Steam or GOG; Xbox/Game Pass saves are on the roadmap).

### 1. Install the server

```bash
# recommended: isolated install
pipx install git+https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link

# or with uv
uv tool install git+https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link

# or plain pip
pip install git+https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link
```

### 2. Check it sees your save

```bash
nms-direct-link --list-saves
nms-direct-link --self-test
```

If nothing is found, point it at your account folder (the one containing `save.hg`):

| Variable | Purpose |
|---|---|
| `NMS_SAVE_DIR` | `…\HelloGames\NMS\st_<steamid>` (Steam) or `…\HelloGames\NMS\DefaultUser` (GOG) |
| `NMS_SAVE_FILE` | A specific `save*.hg` |
| `NMS_SAVE_SLOT` | Prefer one slot (1–15) instead of the newest file |
| `NMS_MAPPING_PATH` | A custom MBINCompiler `mapping.json` |

### 3. Add it to your MCP client

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nms-direct-link": {
      "command": "nms-direct-link"
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add nms-direct-link -- nms-direct-link
```

Any other MCP client: run `nms-direct-link` over stdio, or `nms-direct-link --transport streamable-http --port 5099` for an HTTP endpoint on `127.0.0.1`.

### 4. After a game update

```bash
nms-direct-link --update-mapping
```

This downloads the newest key mapping published with [MBINCompiler](https://github.com/monkeyman192/MBINCompiler) so new save fields decode. If the self-test reports unmapped keys after a patch, run this first.

---

## ◆ Example conversation

> **You:** How am I doing and what should I do about nanites?
>
> **Assistant:** *(calls `nms_get_player_state`, `nms_plan_nanites`)* You're in Euclid on planet 1 of system 427, Normal mode, with 12.5M units and 1,930 nanites. You have **143 discoveries waiting to be uploaded**: that's free nanites before you fly anywhere. After that, the fastest method you can run right now is a Runaway Mould farm; ship scrapping is blocked until you have a bigger units bankroll…
>
> **You:** Is anything on my ship broken, and where's my Chromatic Metal?
>
> **Assistant:** *(calls `nms_audit_tech`, `nms_find_item`)* Your hauler has an S-class and an X-class hyperdrive module installed, nothing damaged. 2,500 Chromatic Metal is in your freighter's main inventory…

---

## ◆ Privacy, safety and the rules

- **Read-only, always.** The server opens `save*.hg` for reading. There is no code path that writes to the save, the game folder, or the game process.
- **Offline by default.** All save tools work without internet. `nms_get_community_mission` calls a public third-party API and sends nothing about you. `--update-mapping` downloads one JSON file from GitHub.
- **No memory reading, no injection, no packet capture.** Those are grey-to-prohibited under the No Man's Sky EULA and are deliberately out of scope.
- **Your data stays yours.** Nothing is logged to disk; logs go to stderr only. The test suite uses a fully synthetic save.
- No Man's Sky © Hello Games. This is an unofficial fan project and is not affiliated with or endorsed by Hello Games.

---

## ◆ Roadmap

| Version | Scope |
|---|---|
| **0.1** (this) | Save-first visibility: state, location, inventories, tech classes, discoveries, fleet, settlements, missions, nanite planning |
| **0.2** | Game-data knowledge base extracted from your own game files (recipes, products, technology, blueprint costs) → `nms_craftable`, richer item names, mission text |
| **0.3** | Galaxy intelligence: economy / wealth / conflict / race prediction for **unvisited** systems from the address (community-verified seed algorithms) → `nms_find_systems` |
| **0.4** | Station observation log: opt-in screenshot + OCR of the technology merchant screen so "where did I see an S-class hyperdrive module?" has an answer → `nms_find_module` |
| later | Xbox / Game Pass (WGS container) saves; price estimation from logged observations |

Not planned: anything that needs to read the running game's memory.

---

## ◆ Tech breakdown

**Save format.** `save*.hg` is a stream of LZ4 blocks, each with a 16-byte header (`0xFEEDA1E5` magic, compressed size, decompressed size ≤ 512 KiB, reserved). Decompressed, it is one JSON document with every key replaced by a 3-character token. The `mf_*.hg` files are XXTEA-encrypted manifests and are not needed for reading.

**De-obfuscation.** Keys are restored with the mapping that ships with MBINCompiler (`mapping.json`, 1,505 entries for libMBIN 7.10.0.1, redistributed unmodified under `src/nms_direct_link/data/` with its LGPL-3.0 licence text). The parser reports any key it could not map, so a new patch shows up as a count in `--self-test` instead of a crash.

**Model.** `SaveSnapshot` (`save/model.py`) is a tolerant typed view: every accessor degrades to empty when a key is missing. Upgrade modules are recognised from their ID (`^UP_HYP4#4242` → family `UP_HYP`, tier `4` → S-class, seed `4242`); the game regenerates module stats from that seed at runtime, so stats are not in the save. Discovery backlog counts only records owned by this save's own discovery identities.

**Address math.** `UniverseAddress` (`save/address.py`) handles the packed 64-bit form used by discoveries and bases (X 12 bits, Z 12, Y 8, galaxy 8, system 12, planet 4), portal glyphs (`P SSS YY ZZZ XXX`), signal-booster codes and voxel distances (400 ly per region).

**Server.** Official `mcp` Python SDK 2.x (`MCPServer`), stdio transport by default, stderr-only logging, Pydantic-validated inputs, read-only tool annotations, markdown and JSON responses. A `SaveStore` caches the parsed save and reloads when the file's mtime or size changes.

**Layout.**

```
src/nms_direct_link/
  server.py        MCP tools, resource, CLI
  store.py         newest-save selection + cache
  knowledge.py     curated, dated gameplay knowledge
  community.py     public community-mission API client
  save/
    locate.py      Steam/GOG/Proton save discovery, slot mapping
    decompress.py  LZ4 block stream
    mapping.py     key mapping load / download / (de)obfuscate
    address.py     galactic address math
    model.py       typed save view
  data/            mapping.json (+ its LGPL-3.0 licence)
tests/             synthetic-fixture suite + optional real-save smoke test
```

**Develop.**

```bash
git clone https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link && cd No-Mans-Sky-Direct-Link
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && pytest
NMS_SMOKE_SAVE="%APPDATA%\HelloGames\NMS\st_<id>\save.hg" pytest tests/test_real_save_smoke.py
```

---

## ◆ Credits

- [MBINCompiler / libMBIN](https://github.com/monkeyman192/MBINCompiler) by monkeyman192 — the key mapping and the decoded game structures (LGPL-3.0; `mapping.json` redistributed unmodified).
- [NMS Copilot](https://github.com/oxur/nms-copilot) by oxur — the Rust save-reading MCP that proved the approach and documented the LZ4/XXTEA/address layout (Apache-2.0).
- [libNOM.io](https://github.com/zencq/libNOM.io) and [NomNom](https://github.com/zencq/NomNom) by zencq — save format constants and version arithmetic (GPL-3.0; constants only, no code reused).
- [NMSCD](https://github.com/NMSCD) and the No Man's Sky modding community — coordinate conventions and years of documentation.
- [Assistant for No Man's Sky](https://nmsassistant.com) by Khaoz-Topsy — the public community-mission endpoint.

## License

MIT — see [LICENSE](LICENSE). No Man's Sky is a trademark of Hello Games Ltd.
