"""Community-mission progress from the Assistant for No Man's Sky public API.

This is the only network call in the server, it is read-only, and it never sends anything about
your save. Endpoint verified 2026-11-08: ``GET https://api.nmsassistant.com/HelloGames/CommunityMission/``.
"""

from __future__ import annotations

from typing import Any

import httpx

COMMUNITY_MISSION_URL = "https://api.nmsassistant.com/HelloGames/CommunityMission/"
USER_AGENT = "nms-direct-link (+https://github.com/Zeekeey-jpeg/No-Mans-Sky-Direct-Link)"


async def fetch_community_mission(timeout: float = 10.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        r = await client.get(COMMUNITY_MISSION_URL)
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise ValueError("unexpected response shape")
    return {
        "mission_id": data.get("missionId"),
        "current_tier": data.get("currentTier"),
        "total_tiers": data.get("totalTiers"),
        "percentage": data.get("percentage"),
        "source": COMMUNITY_MISSION_URL,
    }
