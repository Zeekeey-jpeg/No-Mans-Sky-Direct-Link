"""Optional smoke test against a real save. Skipped unless NMS_SMOKE_SAVE points at a save*.hg.

Nothing from the real save is written or asserted by value; only that it parses cleanly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nms_direct_link.save import load_snapshot

REAL = os.environ.get("NMS_SMOKE_SAVE")

pytestmark = pytest.mark.skipif(not REAL or not Path(REAL or "").is_file(), reason="set NMS_SMOKE_SAVE to a real save*.hg")


def test_real_save_parses():
    snap = load_snapshot(REAL)
    assert snap.version > 4000
    assert isinstance(snap.units, int) and isinstance(snap.nanites, int)
    assert snap.address.portal()
    assert snap.inventories()
    b = snap.discovery_backlog()
    assert b["total_records"] >= b["own_records"] >= b["pending_upload"] >= 0
    # the vendored mapping should cover the whole save; a handful of unknown keys is tolerated after a new patch
    assert len(snap.unknown_keys) < 50, sorted(snap.unknown_keys)[:20]
