"""Checkpoint registry for the Models panel."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend import config


@dataclass
class ModelEntry:
    name: str
    path: str
    size_bytes: int | None
    mtime: str | None
    status: str  # "ready" | "not found"
    documented_expected: bool
    note: str


def _stat_entry(name: str, path: Path, documented: bool, note: str) -> ModelEntry:
    try:
        if path.is_file():
            st = path.stat()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            return ModelEntry(
                name=name,
                path=str(path),
                size_bytes=st.st_size,
                mtime=mtime,
                status="ready",
                documented_expected=documented,
                note=note,
            )
    except OSError:
        pass
    return ModelEntry(
        name=name,
        path=str(path),
        size_bytes=None,
        mtime=None,
        status="not found",
        documented_expected=documented,
        note=note,
    )


def list_models() -> List[Dict[str, Any]]:
    coco_note = (
        "Documented expected prod COCO v5 path. "
        "Override with COCO_V5_CHECKPOINT if a real file is available."
    )
    face_note = (
        "Face v6 path was UNKNOWN on the original host; sandbox placeholder only. "
        "Override with FACE_V6_CHECKPOINT if a real file is available. UNVERIFIED."
    )
    entries = [
        _stat_entry("COCO video model v5 (EfficientNet-B4)", config.COCO_V5_CHECKPOINT, True, coco_note),
        _stat_entry("Face model v6", config.FACE_V6_CHECKPOINT, True, face_note),
    ]
    return [asdict(e) for e in entries]


def missing_checkpoints() -> List[str]:
    missing: List[str] = []
    for entry in list_models():
        if entry["status"] != "ready":
            missing.append(f"{entry['name']}: {entry['path']}")
    return missing


def any_checkpoint_ready() -> bool:
    return any(e["status"] == "ready" for e in list_models())


def env_override_used() -> Dict[str, bool]:
    return {
        "COCO_V5_CHECKPOINT": "COCO_V5_CHECKPOINT" in os.environ,
        "FACE_V6_CHECKPOINT": "FACE_V6_CHECKPOINT" in os.environ,
    }
