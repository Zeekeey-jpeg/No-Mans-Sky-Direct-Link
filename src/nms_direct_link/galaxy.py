"""Galaxy atlas built from the save: visited systems, planets with biomes, route planning, stats.

Everything here comes from discovery records already in your save. Planet records carry two
values in ``DD.VP``: a seed, then a flags word whose low 16 bits are the biome index and whose
bit 16 marks an infested planet. Custom names you gave systems and planets live in ``DM.CN``.

Route planning works over systems you have visited. With a warp range, each leg is a shortest
path through known systems where every hop fits the range (Dijkstra). When known systems cannot
bridge a gap, the leg falls back to the straight-line jump count, since space between charted
systems is full of uncharted stars you can warp through.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

from .save.address import UniverseAddress
from .save.model import SaveSnapshot

BIOMES = {
    0: "Lush", 1: "Toxic", 2: "Scorched", 3: "Radioactive", 4: "Frozen", 5: "Barren", 6: "Dead",
    7: "Weird", 8: "Red", 9: "Green", 10: "Blue", 12: "Swamp", 13: "Lava", 14: "Waterworld", 15: "Gas Giant",
}
BIOME_ALIASES = {
    "paradise": "Lush", "lush": "Lush", "toxic": "Toxic", "scorched": "Scorched", "hot": "Scorched",
    "radioactive": "Radioactive", "frozen": "Frozen", "cold": "Frozen", "barren": "Barren", "desert": "Barren",
    "dead": "Dead", "weird": "Weird", "exotic": "Weird", "red": "Red", "green": "Green", "blue": "Blue",
    "swamp": "Swamp", "lava": "Lava", "volcanic": "Lava", "waterworld": "Waterworld", "ocean": "Waterworld",
    "water": "Waterworld", "gas giant": "Gas Giant", "gasgiant": "Gas Giant", "gas_giant": "Gas Giant",
}

SystemKey = tuple[int, int, int, int, int]


def normalise_biome(name: str) -> str | None:
    return BIOME_ALIASES.get(name.strip().lower().replace("-", " "))


def _as_int(v: Any) -> int | None:
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return int(v, 16) if v.lower().startswith("0x") else int(v)
    except ValueError:
        return None
    return None


@dataclass
class Planet:
    index: int
    biome: str | None = None
    infested: bool = False
    name: str | None = None
    seed: str | None = None
    fauna: int = 0
    flora: int = 0
    minerals: int = 0
    base_names: list[str] = field(default_factory=list)

    def label(self) -> str:
        return self.name or f"planet {self.index}"

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "name": self.name, "biome": self.biome, "infested": self.infested,
                "fauna_discovered": self.fauna, "flora_discovered": self.flora, "minerals_discovered": self.minerals,
                "bases": self.base_names}


@dataclass
class System:
    address: UniverseAddress
    name: str | None = None
    discoverer: str | None = None
    timestamp: int = 0
    planets: dict[int, Planet] = field(default_factory=dict)
    discoveries: int = 0
    pending_upload: int = 0
    base_names: list[str] = field(default_factory=list)
    teleporters: list[str] = field(default_factory=list)

    @property
    def key(self) -> SystemKey:
        return self.address.system_key()

    def label(self) -> str:
        return self.name or f"system {self.address.system:03X} @ {self.address.booster()}"

    def planet(self, index: int) -> Planet:
        if index not in self.planets:
            self.planets[index] = Planet(index=index)
        return self.planets[index]

    def to_dict(self, here: UniverseAddress | None = None) -> dict[str, Any]:
        sys_addr = UniverseAddress(self.address.galaxy, self.address.x, self.address.y, self.address.z, self.address.system, 0)
        d = {
            "name": self.name, "label": self.label(), "portal": sys_addr.portal(), "signal_booster": sys_addr.booster(),
            "galaxy": sys_addr.galaxy_name(), "discoverer": self.discoverer, "discoveries": self.discoveries,
            "pending_upload": self.pending_upload, "bases": self.base_names, "teleporters": self.teleporters,
            "planets": [p.to_dict() for p in sorted(self.planets.values(), key=lambda p: p.index)],
        }
        if here is not None:
            d["distance_ly"] = round(here.distance_ly(self.address))
        return d


class Atlas:
    """All systems this save knows about, indexed for search and routing."""

    def __init__(self, snap: SaveSnapshot) -> None:
        self.snap = snap
        self.here = snap.address
        self.systems: dict[SystemKey, System] = {}
        self._build()

    # ---- build --------------------------------------------------------
    def _system(self, addr: UniverseAddress) -> System:
        k = addr.system_key()
        if k not in self.systems:
            self.systems[k] = System(address=UniverseAddress(addr.galaxy, addr.x, addr.y, addr.z, addr.system, 0))
        return self.systems[k]

    def _build(self) -> None:
        dm = self.snap.data.get("DiscoveryManagerData") or {}
        records = ((dm.get("DiscoveryData-v1") or {}).get("Store") or {}).get("Record") or []
        own = self.snap.own_discovery_owner_ids()
        for r in records:
            if not isinstance(r, dict):
                continue
            dd = r.get("DD") or {}
            try:
                addr = UniverseAddress.from_packed(dd.get("UA", 0))
            except (TypeError, ValueError):
                continue
            kind = str(dd.get("DT", ""))
            ows = r.get("OWS") or {}
            name = (r.get("DM") or {}).get("CN") or None
            sysrec = self._system(addr)
            sysrec.discoveries += 1
            uploaded = int((r.get("FL") or {}).get("U", 0) or 0) > 0
            if not uploaded and (not own or str(ows.get("UID", "")) in own):
                sysrec.pending_upload += 1
            if kind == "SolarSystem":
                sysrec.name = sysrec.name or name
                sysrec.discoverer = sysrec.discoverer or (ows.get("USN") or None)
                sysrec.timestamp = sysrec.timestamp or int(ows.get("TS", 0) or 0)
            elif kind == "Planet":
                p = sysrec.planet(addr.planet)
                p.name = p.name or name
                vp = dd.get("VP") or []
                if vp:
                    p.seed = str(vp[0])
                if len(vp) > 1:
                    flags = _as_int(vp[1])
                    if flags is not None:
                        p.biome = BIOMES.get(flags & 0xFFFF)
                        p.infested = bool((flags >> 16) & 1)
            elif kind in ("Animal", "Flora", "Mineral"):
                p = sysrec.planet(addr.planet)
                if kind == "Animal":
                    p.fauna += 1
                elif kind == "Flora":
                    p.flora += 1
                else:
                    p.minerals += 1
        for b in self.snap.bases():
            if not b.get("address"):
                continue
            addr = UniverseAddress.from_packed(b["address"]["packed"])
            s = self._system(addr)
            s.base_names.append(b["name"])
            if b["type"] == "HomePlanetBase":
                s.planet(addr.planet).base_names.append(b["name"])
        for t in self.snap.teleporters():
            if t.get("address"):
                addr = UniverseAddress.from_packed(t["address"]["packed"])
                self._system(addr).teleporters.append(f"{t['name']} [{t['type']}]")
        self._system(self.here)  # always include where the player is

    # ---- lookup -------------------------------------------------------
    def find_system(self, query: str) -> System | None:
        q = query.strip()
        ql = q.lower()
        if ql in ("here", "current", "me", "player"):
            return self.systems.get(self.here.system_key())
        addr = None
        try:
            if len(q.replace(" ", "")) == 12:
                addr = UniverseAddress.from_portal(q)
            elif ":" in q:
                addr = UniverseAddress.from_booster(q)
            elif ql.startswith("0x") or q.isdigit():
                addr = UniverseAddress.from_packed(q)
        except (ValueError, TypeError):
            addr = None
        if addr is not None:
            s = self.systems.get(addr.system_key())
            if s:
                return s
            for s in self.systems.values():  # booster codes carry no galaxy; match coordinates only
                if s.key[1:] == addr.system_key()[1:]:
                    return s
        for s in self.systems.values():
            if s.name and s.name.lower() == ql:
                return s
        for s in self.systems.values():
            if any(b.lower() == ql for b in s.base_names) or any(t.lower().startswith(ql) for t in s.teleporters):
                return s
        for s in self.systems.values():
            if (s.name and ql in s.name.lower()) or any(ql in b.lower() for b in s.base_names):
                return s
        return None

    def origin(self, from_base: str | None) -> tuple[UniverseAddress, str]:
        if not from_base:
            return self.here, "your position"
        s = self.find_system(from_base)
        if s is None:
            raise ValueError(f"no base or system called '{from_base}' in this save")
        return s.address, s.label()

    # ---- search -------------------------------------------------------
    def search_planets(self, biome: str | None = None, infested: bool | None = None, named_only: bool = False,
                       within_ly: float | None = None, from_base: str | None = None, discoverer: str | None = None,
                       with_base: bool = False, limit: int = 20) -> dict[str, Any]:
        origin, origin_label = self.origin(from_base)
        want = normalise_biome(biome) if biome else None
        if biome and not want:
            raise ValueError(f"unknown biome '{biome}'. Try: {', '.join(sorted(set(BIOMES.values())))}")
        hits = []
        for s in self.systems.values():
            if s.address.galaxy != origin.galaxy:
                continue
            dist = origin.distance_ly(s.address)
            if within_ly is not None and dist > within_ly:
                continue
            if discoverer and not (s.discoverer and discoverer.lower() in s.discoverer.lower()):
                continue
            for p in s.planets.values():
                if want and p.biome != want:
                    continue
                if infested is not None and p.infested != infested:
                    continue
                if named_only and not p.name:
                    continue
                if with_base and not p.base_names:
                    continue
                if not (p.biome or p.name or p.fauna or p.flora or p.minerals or p.base_names):
                    continue
                paddr = UniverseAddress(s.address.galaxy, s.address.x, s.address.y, s.address.z, s.address.system, p.index)
                hits.append({"system": s.label(), "planet": p.label(), "portal": paddr.portal(), "distance_ly": round(dist), **p.to_dict()})
        hits.sort(key=lambda h: (h["distance_ly"], h["system"], h["index"]))
        return {"origin": origin_label, "total": len(hits), "count": min(len(hits), limit), "has_more": len(hits) > limit,
                "results": hits[:limit]}

    def nearby(self, count: int = 10, biome: str | None = None, from_base: str | None = None) -> list[dict[str, Any]]:
        origin, _ = self.origin(from_base)
        want = normalise_biome(biome) if biome else None
        out = []
        for s in self.systems.values():
            if s.address.galaxy != origin.galaxy:
                continue
            if want and not any(p.biome == want for p in s.planets.values()):
                continue
            d = s.to_dict(origin)
            d["distance_ly"] = round(origin.distance_ly(s.address))
            d["here"] = s.key == self.here.system_key()
            out.append(d)
        out.sort(key=lambda d: d["distance_ly"])
        return out[:count]

    # ---- stats --------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        biomes: dict[str, int] = {}
        planets = infested = named_p = unknown = 0
        for s in self.systems.values():
            for p in s.planets.values():
                planets += 1
                if p.biome:
                    biomes[p.biome] = biomes.get(p.biome, 0) + 1
                else:
                    unknown += 1
                infested += p.infested
                named_p += bool(p.name)
        dists = [(self.here.distance_ly(s.address), s) for s in self.systems.values() if s.address.galaxy == self.here.galaxy]
        far = max(dists, key=lambda t: t[0]) if dists else None
        disc = self.snap.discoveries()
        by_type: dict[str, int] = {}
        for d in disc:
            by_type[d.kind] = by_type.get(d.kind, 0) + 1
        centre = [s.address.distance_to_centre_ly() for s in self.systems.values()]
        galaxies = sorted({s.address.galaxy_name() for s in self.systems.values()})
        return {
            "systems": len(self.systems), "named_systems": sum(1 for s in self.systems.values() if s.name),
            "planets": planets, "named_planets": named_p, "infested_planets": infested, "unknown_biome": unknown,
            "biomes": dict(sorted(biomes.items(), key=lambda kv: -kv[1])), "bases": len(self.snap.bases()),
            "teleporters": len(self.snap.teleporters()), "discoveries_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "galaxies_visited": galaxies,
            "farthest_system": {"label": far[1].label(), "distance_ly": round(far[0])} if far else None,
            "closest_to_centre_ly": round(min(centre)) if centre else None,
        }

    # ---- routing ------------------------------------------------------
    def _neighbours(self, galaxy: int, warp: float) -> dict[SystemKey, list[tuple[SystemKey, float]]]:
        """Systems within warp range of each other, computed once per route request."""
        nodes = [(k, s.address) for k, s in self.systems.items() if s.address.galaxy == galaxy]
        adj: dict[SystemKey, list[tuple[SystemKey, float]]] = {k: [] for k, _ in nodes}
        for i, (ka, a) in enumerate(nodes):
            for kb, b in nodes[i + 1:]:
                w = a.distance_ly(b)
                if w <= warp:
                    adj[ka].append((kb, w))
                    adj[kb].append((ka, w))
        return adj

    def _dijkstra(self, start: SystemKey, goal: SystemKey, adj: dict[SystemKey, list[tuple[SystemKey, float]]]) -> tuple[list[SystemKey], float] | None:
        dist = {start: 0.0}
        prev: dict[SystemKey, SystemKey] = {}
        heap = [(0.0, start)]
        seen: set[SystemKey] = set()
        while heap:
            d, u = heapq.heappop(heap)
            if u in seen:
                continue
            seen.add(u)
            if u == goal:
                path = [u]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return list(reversed(path)), d
            for v, w in adj.get(u, ()):
                if v in seen:
                    continue
                if d + w < dist.get(v, math.inf):
                    dist[v] = d + w
                    prev[v] = u
                    heapq.heappush(heap, (d + w, v))
        return None

    @staticmethod
    def _tour_length(points: list[UniverseAddress], order: list[int], round_trip: bool) -> float:
        seq = [0] + order + ([0] if round_trip else [])
        return sum(points[a].distance_ly(points[b]) for a, b in zip(seq, seq[1:], strict=False))

    def _order(self, points: list[UniverseAddress], algorithm: str, round_trip: bool) -> list[int]:
        remaining = list(range(1, len(points)))
        order: list[int] = []
        cur = 0
        while remaining:
            nxt = min(remaining, key=lambda i: points[cur].distance_ly(points[i]))
            order.append(nxt)
            remaining.remove(nxt)
            cur = nxt
        if algorithm == "2opt" and len(order) > 2:
            best = self._tour_length(points, order, round_trip)
            improved = True
            while improved:
                improved = False
                for i in range(len(order) - 1):
                    for j in range(i + 1, len(order)):
                        cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                        length = self._tour_length(points, cand, round_trip)
                        if length + 1e-6 < best:
                            order, best, improved = cand, length, True
        return order

    def plan_route(self, targets: list[str] | None = None, biome: str | None = None, from_base: str | None = None,
                   warp_range: float | None = None, within_ly: float | None = None, max_targets: int = 10,
                   algorithm: str = "2opt", round_trip: bool = False) -> dict[str, Any]:
        origin, origin_label = self.origin(from_base)
        stops: list[System] = []
        missing: list[str] = []
        for t in targets or []:
            s = self.find_system(t)
            (stops.append(s) if s else missing.append(t))
        if biome:
            want = normalise_biome(biome)
            if not want:
                raise ValueError(f"unknown biome '{biome}'")
            for s in self.systems.values():
                if s.address.galaxy == origin.galaxy and any(p.biome == want for p in s.planets.values()):
                    if within_ly is None or origin.distance_ly(s.address) <= within_ly:
                        stops.append(s)
        uniq: dict[SystemKey, System] = {}
        for s in stops:
            if s.key != origin.system_key():
                uniq.setdefault(s.key, s)
        stops = sorted(uniq.values(), key=lambda s: origin.distance_ly(s.address))[:max_targets]
        if not stops:
            return {"origin": origin_label, "legs": [], "total_ly": 0, "missing": missing,
                    "note": "no targets matched (route planning covers systems recorded in your save)"}
        points = [origin] + [s.address for s in stops]
        order = self._order(points, algorithm, round_trip)
        seq = [0] + order + ([0] if round_trip else [])
        labels = [origin_label] + [s.label() for s in stops]
        keys = [self.systems.get(origin.system_key(), System(origin)).key] + [s.key for s in stops]
        legs = []
        total = 0.0
        total_jumps = 0
        teleport_hint = None
        adj = self._neighbours(origin.galaxy, warp_range) if warp_range else {}
        for a, b in zip(seq, seq[1:], strict=False):
            straight = points[a].distance_ly(points[b])
            leg: dict[str, Any] = {"from": labels[a], "to": labels[b], "straight_ly": round(straight)}
            if warp_range:
                path = self._dijkstra(keys[a], keys[b], adj) if keys[a] in self.systems and keys[b] in self.systems else None
                if path:
                    hops, length = path
                    leg.update({"via_known_systems": [self.systems[k].label() for k in hops[1:-1]], "path_ly": round(length),
                                "jumps": len(hops) - 1})
                else:
                    leg.update({"via_known_systems": [], "path_ly": round(straight), "jumps": max(1, math.ceil(straight / warp_range)),
                                "note": "no chain of visited systems fits your range; warp through uncharted stars"})
                total_jumps += leg["jumps"]
                total += leg["path_ly"]
            else:
                total += straight
            legs.append(leg)
        # Teleporter shortcut: if a teleporter system sits closer to the first stop than you do, say so.
        first = points[seq[1]]
        best_tp = None
        for s in self.systems.values():
            if s.teleporters and s.address.galaxy == first.galaxy:
                d = s.address.distance_ly(first)
                if d < points[0].distance_ly(first) and (best_tp is None or d < best_tp[0]):
                    best_tp = (d, s)
        if best_tp:
            teleport_hint = {"teleport_to": best_tp[1].label(), "teleporters": best_tp[1].teleporters,
                             "then_ly": round(best_tp[0]), "saves_ly": round(points[0].distance_ly(first) - best_tp[0])}
        return {"origin": origin_label, "algorithm": algorithm, "round_trip": round_trip, "warp_range_ly": warp_range,
                "stops": len(stops), "legs": legs, "total_ly": round(total), "total_jumps": total_jumps if warp_range else None,
                "teleport_shortcut": teleport_hint, "missing": missing}
