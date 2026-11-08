"""Key de-obfuscation for No Man's Sky save JSON.

The game writes every JSON key as a short obfuscated token (``"F2P"`` instead of ``"Version"``).
The community-maintained mapping ships with MBINCompiler (monkeyman192/MBINCompiler, LGPL-3.0; redistributed unmodified) as a
``mapping.json`` release asset. A copy is vendored in ``data/mapping.json``; a newer one can be
downloaded with ``nms-direct-link --update-mapping`` or pointed to with ``NMS_MAPPING_PATH``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

OBFUSCATED_VERSION_KEY = "F2P"
READABLE_VERSION_KEY = "Version"
MAPPING_ENV = "NMS_MAPPING_PATH"
RELEASES_API = "https://api.github.com/repos/monkeyman192/MBINCompiler/releases"


def user_cache_dir() -> Path:
    """Per-user cache directory for downloaded mappings."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "nms-direct-link"


@dataclass
class KeyMapping:
    """Bidirectional obfuscated <-> readable key map."""

    version: str
    forward: dict[str, str] = field(repr=False)  # obfuscated -> readable
    source: str = "bundled"
    _reverse: dict[str, str] | None = field(default=None, repr=False)

    @property
    def reverse(self) -> dict[str, str]:
        if self._reverse is None:
            self._reverse = {v: k for k, v in self.forward.items()}
        return self._reverse

    def __len__(self) -> int:
        return len(self.forward)

    @classmethod
    def from_json(cls, payload: dict[str, Any], source: str) -> KeyMapping:
        entries = payload.get("Mapping") or payload.get("mapping") or []
        forward = {e["Key"]: e["Value"] for e in entries}
        if not forward:
            raise ValueError(f"mapping at {source} has no entries")
        return cls(version=str(payload.get("libMBIN_version", "unknown")), forward=forward, source=source)

    def deobfuscate(self, obj: Any, unknown: set[str] | None = None) -> Any:
        """Recursively rename keys. Unknown keys are kept as-is and reported in ``unknown``."""
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                nk = self.forward.get(k)
                if nk is None:
                    if unknown is not None:
                        unknown.add(k)
                    nk = k
                out[nk] = self.deobfuscate(v, unknown)
            return out
        if isinstance(obj, list):
            return [self.deobfuscate(x, unknown) for x in obj]
        return obj

    def obfuscate(self, obj: Any) -> Any:
        """Inverse of :meth:`deobfuscate`; used to build synthetic test saves."""
        if isinstance(obj, dict):
            return {self.reverse.get(k, k): self.obfuscate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.obfuscate(x) for x in obj]
        return obj


def is_obfuscated(obj: dict[str, Any]) -> bool:
    return OBFUSCATED_VERSION_KEY in obj and READABLE_VERSION_KEY not in obj


def _bundled_path() -> Path:
    return Path(str(resources.files("nms_direct_link").joinpath("data", "mapping.json")))


def mapping_candidates() -> list[tuple[str, Path]]:
    """Search order: env override, user cache (downloaded), bundled."""
    out: list[tuple[str, Path]] = []
    env = os.environ.get(MAPPING_ENV)
    if env:
        out.append(("env", Path(env)))
    out.append(("cache", user_cache_dir() / "mapping.json"))
    out.append(("bundled", _bundled_path()))
    return out


def load_mapping(path: str | Path | None = None) -> KeyMapping:
    """Load the first readable mapping. ``path`` forces a specific file."""
    if path is not None:
        p = Path(path)
        return KeyMapping.from_json(json.loads(p.read_text(encoding="utf-8")), source=str(p))
    errors: list[str] = []
    for label, p in mapping_candidates():
        if p.is_file():
            try:
                return KeyMapping.from_json(json.loads(p.read_text(encoding="utf-8")), source=f"{label}:{p}")
            except (OSError, ValueError, KeyError) as exc:  # pragma: no cover - defensive
                errors.append(f"{p}: {exc}")
    raise FileNotFoundError("no usable mapping.json found; " + "; ".join(errors))


def download_latest_mapping(include_prerelease: bool = False, timeout: float = 30.0) -> Path:
    """Fetch the newest ``mapping.json`` from MBINCompiler releases into the user cache.

    Only the mapping asset is downloaded; nothing is executed.
    """
    import httpx  # local import keeps the save layer importable without network deps

    dest = user_cache_dir() / "mapping.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nms-direct-link"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        releases = client.get(RELEASES_API, params={"per_page": 10}).raise_for_status().json()
        for rel in releases:
            if rel.get("draft") or (rel.get("prerelease") and not include_prerelease):
                continue
            for asset in rel.get("assets", []):
                if asset.get("name") == "mapping.json":
                    data = client.get(asset["browser_download_url"]).raise_for_status().content
                    KeyMapping.from_json(json.loads(data), source="download")  # validate before saving
                    dest.write_bytes(data)
                    return dest
    raise RuntimeError("no release with a mapping.json asset was found")
