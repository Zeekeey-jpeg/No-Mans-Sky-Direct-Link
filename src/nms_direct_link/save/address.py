"""Galactic address math: voxel coordinates, packed u64 addresses, portal glyphs, signal-booster codes.

Packed u64 layout (as used in discovery records and base records):
    bits 0-11   X  (signed 12-bit)
    bits 12-23  Z  (signed 12-bit)
    bits 24-31  Y  (signed 8-bit)
    bits 32-39  galaxy (RealityIndex)
    bits 40-51  solar system index
    bits 52-55  planet index

Portal address (12 hex glyphs): ``P SSS YY ZZZ XXX`` where
    YY  = (Y + 0x81) & 0xFF
    ZZZ = (Z + 0x801) & 0xFFF
    XXX = (X + 0x801) & 0xFFF
Signal-booster code: ``XXXX:YYYY:ZZZZ:SSSS`` = (X + 0x7FF, Y + 0x7F, Z + 0x7FF, system).
One voxel (region) is treated as 400 light-years for distance estimates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

LY_PER_VOXEL = 400.0

GLYPH_NAMES = [
    "Sunset", "Bird", "Face", "Diplo", "Eclipse", "Balloon", "Boat", "Bug",
    "Dragonfly", "Galaxy", "Voxel", "Fish", "Tent", "Rocket", "Tree", "Atlas",
]

GALAXY_NAMES = [
    "Euclid", "Hilbert Dimension", "Calypso", "Hesperius Dimension", "Hyades", "Ickjamatew",
    "Budullangr", "Kikolgallr", "Eltiensleen", "Eissentam", "Elkupalos", "Aptarkaba",
    "Ontiniangp", "Odiwagiri", "Ogtialabi", "Muhacksonto", "Hitonskyer", "Rerasmutul",
    "Isdoraijung", "Doctinawyra", "Loychazinq", "Zukasizawa", "Ekwathore", "Yeberhahne",
    "Twerbetek", "Sivarates", "Eajerandal", "Aldukesci", "Wotyarogii", "Sudzerbal",
    "Maupenzhay", "Sugueziume", "Brogoweldian", "Ehbogdenbu", "Ijsenufryos", "Nipikulha",
    "Autsurabin", "Lusontrygiamh", "Rewmanawa", "Ethiophodhe", "Urastrykle", "Xobeurindj",
    "Oniijialdu", "Wucetosucc", "Ebyeloof", "Odyavanta", "Milekistri", "Waferganh",
    "Ewcomechio", "Inunnunnoda", "Disterbuld", "Rykelgiloric", "Tenuiarca", "Mirenkolin",
    "Ikwalitt", "Shaupabnu", "Wecaquiten", "Ahdokerstr", "Omutilangzo", "Sephtopigg",
]

_PORTAL_RE = re.compile(r"^[0-9A-Fa-f]{12}$")
_BOOSTER_RE = re.compile(r"^([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})$")


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("bool is not an address")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    raise TypeError(f"cannot interpret {value!r} as a packed address")


@dataclass(frozen=True)
class UniverseAddress:
    galaxy: int
    x: int
    y: int
    z: int
    system: int
    planet: int = 0

    # ---- constructors -------------------------------------------------
    @classmethod
    def from_save(cls, obj: dict[str, Any]) -> UniverseAddress:
        """From the readable ``UniverseAddress`` structure in a save."""
        ga = obj.get("GalacticAddress", obj)
        return cls(
            galaxy=int(obj.get("RealityIndex", 0)),
            x=int(ga.get("VoxelX", 0)),
            y=int(ga.get("VoxelY", 0)),
            z=int(ga.get("VoxelZ", 0)),
            system=int(ga.get("SolarSystemIndex", 0)),
            planet=int(ga.get("PlanetIndex", 0)),
        )

    @classmethod
    def from_packed(cls, value: int | str) -> UniverseAddress:
        v = _to_int(value)
        return cls(
            x=_signed(v & 0xFFF, 12),
            z=_signed((v >> 12) & 0xFFF, 12),
            y=_signed((v >> 24) & 0xFF, 8),
            galaxy=(v >> 32) & 0xFF,
            system=(v >> 40) & 0xFFF,
            planet=(v >> 52) & 0xF,
        )

    @classmethod
    def from_portal(cls, glyphs: str, galaxy: int = 0) -> UniverseAddress:
        g = glyphs.strip().replace(" ", "")
        if not _PORTAL_RE.match(g):
            raise ValueError("portal address must be 12 hex glyphs (0-9, A-F)")
        planet = int(g[0], 16)
        system = int(g[1:4], 16)
        yy, zzz, xxx = int(g[4:6], 16), int(g[6:9], 16), int(g[9:12], 16)
        return cls(
            galaxy=galaxy,
            x=_signed((xxx - 0x801) & 0xFFF, 12),
            y=_signed((yy - 0x81) & 0xFF, 8),
            z=_signed((zzz - 0x801) & 0xFFF, 12),
            system=system,
            planet=planet,
        )

    @classmethod
    def from_booster(cls, code: str, galaxy: int = 0, planet: int = 0) -> UniverseAddress:
        m = _BOOSTER_RE.match(code.strip().upper())
        if not m:
            raise ValueError("signal booster code must look like XXXX:YYYY:ZZZZ:SSSS")
        xxxx, yyyy, zzzz, ssss = (int(p, 16) for p in m.groups())
        return cls(
            galaxy=galaxy, x=xxxx - 0x7FF, y=yyyy - 0x7F, z=zzzz - 0x7FF, system=ssss & 0xFFF, planet=planet
        )

    # ---- conversions --------------------------------------------------
    def packed(self) -> int:
        return (
            (self.x & 0xFFF)
            | ((self.z & 0xFFF) << 12)
            | ((self.y & 0xFF) << 24)
            | ((self.galaxy & 0xFF) << 32)
            | ((self.system & 0xFFF) << 40)
            | ((self.planet & 0xF) << 52)
        )

    def portal(self) -> str:
        yy = (self.y + 0x81) & 0xFF
        zzz = (self.z + 0x801) & 0xFFF
        xxx = (self.x + 0x801) & 0xFFF
        return f"{self.planet & 0xF:X}{self.system & 0xFFF:03X}{yy:02X}{zzz:03X}{xxx:03X}"

    def glyph_names(self) -> list[str]:
        return [GLYPH_NAMES[int(c, 16)] for c in self.portal()]

    def booster(self) -> str:
        return f"{(self.x + 0x7FF) & 0xFFFF:04X}:{(self.y + 0x7F) & 0xFFFF:04X}:{(self.z + 0x7FF) & 0xFFFF:04X}:{self.system & 0xFFFF:04X}"

    def galaxy_name(self) -> str:
        return GALAXY_NAMES[self.galaxy] if 0 <= self.galaxy < len(GALAXY_NAMES) else f"Galaxy {self.galaxy}"

    def system_key(self) -> tuple[int, int, int, int, int]:
        """Identity of the star system (planet dropped)."""
        return (self.galaxy, self.x, self.y, self.z, self.system)

    def distance_ly(self, other: UniverseAddress) -> float:
        """Approximate distance in light-years (400 ly per voxel)."""
        return math.dist((self.x, self.y, self.z), (other.x, other.y, other.z)) * LY_PER_VOXEL

    def distance_to_centre_ly(self) -> float:
        return math.dist((self.x, self.y, self.z), (0, 0, 0)) * LY_PER_VOXEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "galaxy": self.galaxy,
            "galaxy_name": self.galaxy_name(),
            "voxel": {"x": self.x, "y": self.y, "z": self.z},
            "system_index": self.system,
            "planet_index": self.planet,
            "portal": self.portal(),
            "glyphs": self.glyph_names(),
            "signal_booster": self.booster(),
            "packed": self.packed(),
            "distance_to_centre_ly": round(self.distance_to_centre_ly()),
        }

    def __str__(self) -> str:
        return f"{self.galaxy_name()} {self.booster()} planet {self.planet} (portal {self.portal()})"
