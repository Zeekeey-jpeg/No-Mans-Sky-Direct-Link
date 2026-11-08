"""Cached access to the newest save, reloaded when the file changes on disk."""

from __future__ import annotations

import logging
import os
from datetime import UTC
from pathlib import Path

from .save import SaveFile, SaveSnapshot, list_saves, load_mapping, load_snapshot
from .save.mapping import KeyMapping

log = logging.getLogger("nms_direct_link")
SAVE_FILE_ENV = "NMS_SAVE_FILE"
SLOT_ENV = "NMS_SAVE_SLOT"


class NoSaveFound(RuntimeError):
    pass


class SaveStore:
    def __init__(self) -> None:
        self._mapping: KeyMapping | None = None
        self._snapshot: SaveSnapshot | None = None
        self._snapshot_key: tuple[str, float, int] | None = None

    @property
    def mapping(self) -> KeyMapping:
        if self._mapping is None:
            self._mapping = load_mapping()
            log.info("mapping %s (%d keys) from %s", self._mapping.version, len(self._mapping), self._mapping.source)
        return self._mapping

    def pick(self, slot: int | None = None) -> SaveFile:
        explicit = os.environ.get(SAVE_FILE_ENV)
        if explicit and slot is None:
            p = Path(explicit).expanduser()
            if not p.is_file():
                raise NoSaveFound(f"{SAVE_FILE_ENV} points to a missing file: {p}")
            from datetime import datetime

            st = p.stat()
            return SaveFile(path=p, slot=0, kind="explicit", platform="custom", account=p.parent.name,
                            modified=datetime.fromtimestamp(st.st_mtime, tz=UTC), size=st.st_size)
        if slot is None:
            env_slot = os.environ.get(SLOT_ENV)
            slot = int(env_slot) if env_slot and env_slot.isdigit() else None
        saves = list_saves()
        if slot is not None:
            saves = [s for s in saves if s.slot == slot]
        if not saves:
            raise NoSaveFound(
                "No No Man's Sky save found. Set NMS_SAVE_DIR to your HelloGames\\NMS\\<account> folder, "
                "or NMS_SAVE_FILE to a specific save*.hg."
            )
        return saves[0]

    def snapshot(self, slot: int | None = None, force: bool = False) -> SaveSnapshot:
        sf = self.pick(slot)
        st = sf.path.stat()
        key = (str(sf.path), st.st_mtime, st.st_size)
        if force or self._snapshot is None or key != self._snapshot_key:
            log.info("loading save %s (%s)", sf.path.name, sf.label)
            self._snapshot = load_snapshot(sf.path, self.mapping)
            self._snapshot_key = key
        return self._snapshot
