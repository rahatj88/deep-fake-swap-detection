"""Sandbox dashboard configuration. Defaults are clearly labeled UNVERIFIED."""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ---
REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / "tmp"
FRONTEND_DIR = REPO_ROOT / "frontend"
REVIEW_MD = REPO_ROOT / "REVIEW.md"

# Documented expected prod paths (may not exist in sandbox)
DEFAULT_COCO_V5_PATH = Path(
    "/home/deepfake/deeptrace_data/coco_v5_effb4/coco_effb4_best.pt"
)
# Face v6 path was UNKNOWN on the original host; placeholder for sandbox docs only.
DEFAULT_FACE_V6_PATH = Path("/home/deepfake/deeptrace_data/face_v6/face_v6_best.pt")

COCO_V5_CHECKPOINT = Path(
    os.environ.get("COCO_V5_CHECKPOINT", str(DEFAULT_COCO_V5_PATH))
)
FACE_V6_CHECKPOINT = Path(
    os.environ.get("FACE_V6_CHECKPOINT", str(DEFAULT_FACE_V6_PATH))
)

# --- Hybrid rule DEFAULTS — NOT confirmed by owner ---
# See ASSUMPTIONS.md. Hybrid rule reconstructed as face-vs-coco branch; NOT confirmed by owner.
COCO_THRESHOLD = float(os.environ.get("COCO_THRESHOLD", "0.50"))
FACE_THRESHOLD = float(os.environ.get("FACE_THRESHOLD", "0.55"))
FACE_REAL_FLOOR = float(os.environ.get("FACE_REAL_FLOOR", "0.35"))

# --- Upload / inference limits ---
MAX_UPLOAD_MB = float(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024)
ALLOWED_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv"})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "application/octet-stream",  # browsers often omit precise video MIME
    }
)
MAX_FRAMES = int(os.environ.get("MAX_FRAMES", "300"))
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "8"))
INFERENCE_TIMEOUT_SEC = float(os.environ.get("INFERENCE_TIMEOUT_SEC", "60"))

# --- Rate limits / history ---
ANALYZE_RATE_PER_MIN = int(os.environ.get("ANALYZE_RATE_PER_MIN", "5"))
GLOBAL_RATE_PER_MIN = int(os.environ.get("GLOBAL_RATE_PER_MIN", "60"))
HISTORY_CAP = int(os.environ.get("HISTORY_CAP", "50"))

# --- Server ---
HOST = "127.0.0.1"
PORT = 8001
API_VERSION = "sandbox-0.1.0"

# Force mock even if torch is present
FORCE_MOCK = os.environ.get("FORCE_MOCK", "1").lower() in {"1", "true", "yes"}
