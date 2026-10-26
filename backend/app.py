"""FastAPI sandbox dashboard: JSON API + single-page UI on 127.0.0.1:8001."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Deque, Dict, List

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.inference import InferenceTimeout, analyze_with_timeout, get_backend
from backend.models_registry import list_models, missing_checkpoints
from backend.security import (
    analyze_limiter,
    error_response,
    extension_allowed,
    global_limiter,
    make_upload_dir,
    safe_join_upload,
    sanitize_filename,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("dashboard")

STARTED_AT = time.time()
HISTORY: Deque[Dict[str, Any]] = deque(maxlen=config.HISTORY_CAP)


def _gpu_info() -> Dict[str, Any]:
    """Best-effort nvidia-smi parse; nulls when unavailable. Never invent metrics."""
    try:
        import subprocess

        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {"available": False, "name": None, "memory_total_mb": None, "memory_free_mb": None}
        line = proc.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return {"available": False, "name": None, "memory_total_mb": None, "memory_free_mb": None}
        return {
            "available": True,
            "name": parts[0],
            "memory_total_mb": float(parts[1]),
            "memory_free_mb": float(parts[2]),
        }
    except (FileNotFoundError, OSError, ValueError, subprocess.TimeoutExpired):
        return {"available": False, "name": None, "memory_total_mb": None, "memory_free_mb": None}


def _disk_info() -> Dict[str, Any]:
    usage = shutil.disk_usage(config.REPO_ROOT)
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


def _cpu_load() -> Dict[str, Any]:
    try:
        load1, load5, load15 = os.getloadavg()
        return {"load1": load1, "load5": load5, "load15": load15}
    except (OSError, AttributeError):
        return {"load1": None, "load5": None, "load15": None}


def _unverified_items() -> List[str]:
    items: List[str] = []
    items.extend(f"Missing checkpoint — {m}" for m in missing_checkpoints())
    items.append(
        "Hybrid rule reconstructed as face-vs-coco branch; NOT confirmed by owner."
    )
    backend = get_backend()
    if backend.mode == "mock":
        items.append("Mock inference active — scores are deterministic hashes, NOT real ML.")
    items.append("Sandbox mode — do not treat results as production deepfake accuracy.")
    return items


def parse_findings() -> List[Dict[str, str]]:
    """Parse REVIEW.md table rows. Hard-capped lines."""
    path = config.REVIEW_MD
    findings: List[Dict[str, str]] = []
    if not path.is_file():
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lines = text.splitlines()
    max_lines = min(len(lines), 500)
    in_table = False
    for i in range(max_lines):
        line = lines[i].strip()
        if line.startswith("|") and "Severity" in line and "Where" in line:
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line.replace("|", "").strip()) <= {"-", ":", " "}:
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 5:
                findings.append(
                    {
                        "severity": cols[0],
                        "where": cols[1],
                        "what": cols[2],
                        "exploit": cols[3],
                        "fix": cols[4],
                    }
                )
            if len(findings) >= 100:
                break
    return findings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    get_backend()  # init once
    logger.info(
        "Sandbox dashboard starting on %s:%s mode=%s",
        config.HOST,
        config.PORT,
        get_backend().mode,
    )
    yield


app = FastAPI(title="Deepfake Dashboard Sandbox", version=config.API_VERSION, lifespan=lifespan)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    allowed, retry = global_limiter.check(request)
    if not allowed:
        return error_response(
            429,
            "rate_limited",
            "Too many requests. Slow down.",
            **{"Retry-After": str(retry)},
        )
    return await call_next(request)


@app.get("/api/health")
def api_health() -> Dict[str, Any]:
    return {
        "gpu": _gpu_info(),
        "disk": _disk_info(),
        "cpu": _cpu_load(),
        "uptime_sec": round(time.time() - STARTED_AT, 2),
        "version": config.API_VERSION,
        "host": platform.node(),
        "platform": platform.platform(),
        "inference_mode": get_backend().mode,
        "unverified": _unverified_items(),
        "bind": f"{config.HOST}:{config.PORT}",
    }


@app.get("/api/models")
def api_models() -> Dict[str, Any]:
    return {
        "models": list_models(),
        "hybrid_defaults": {
            "coco_threshold": config.COCO_THRESHOLD,
            "face_threshold": config.FACE_THRESHOLD,
            "face_real_floor": config.FACE_REAL_FLOOR,
            "note": "Hybrid rule reconstructed as face-vs-coco branch; NOT confirmed by owner.",
        },
        "limits": {
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "max_frames": config.MAX_FRAMES,
            "max_batch_size": config.MAX_BATCH_SIZE,
            "inference_timeout_sec": config.INFERENCE_TIMEOUT_SEC,
            "history_cap": config.HISTORY_CAP,
        },
    }


@app.post("/api/analyze")
async def api_analyze(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    allowed, retry = analyze_limiter.check(request)
    if not allowed:
        return error_response(
            429,
            "analyze_rate_limited",
            "Analyze rate limit exceeded (default 5/min).",
            **{"Retry-After": str(retry)},
        )

    raw_name = file.filename or "upload.bin"
    safe_name = sanitize_filename(raw_name)
    if not extension_allowed(safe_name):
        return error_response(
            400,
            "invalid_type",
            "Allowed types: mp4, mov, avi, mkv.",
        )

    upload_dir: Path | None = None
    dest: Path | None = None
    try:
        upload_dir = make_upload_dir()
        dest = safe_join_upload(upload_dir, safe_name)
        # Stream to disk with hard size cap — do not load whole file into memory
        written = 0
        chunk_size = 64 * 1024
        max_chunks = (config.MAX_UPLOAD_BYTES // chunk_size) + 2
        with dest.open("wb") as out:
            for _ in range(max_chunks):
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > config.MAX_UPLOAD_BYTES:
                    out.close()
                    return error_response(
                        413,
                        "payload_too_large",
                        f"File exceeds max size of {config.MAX_UPLOAD_MB} MB.",
                    )
                out.write(chunk)
            else:
                # Hit max_chunks without EOF — treat as oversize / abort
                return error_response(
                    413,
                    "payload_too_large",
                    f"File exceeds max size of {config.MAX_UPLOAD_MB} MB.",
                )

        if written == 0:
            return error_response(400, "empty_file", "Uploaded file is empty.")

        try:
            result = analyze_with_timeout(dest, safe_name)
        except InferenceTimeout:
            return error_response(
                504,
                "inference_timeout",
                f"Inference exceeded {config.INFERENCE_TIMEOUT_SEC}s timeout.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("analyze_failed")
            return error_response(500, "analyze_failed", "Analysis failed.")

        payload = result.to_dict()
        # History: append; deque maxlen enforces HISTORY_CAP
        HISTORY.appendleft(
            {
                "filename": payload["filename"],
                "decision": payload["decision"],
                "confidence": payload["confidence"],
                "elapsed_sec": payload["elapsed_sec"],
                "inference_mode": payload["inference_mode"],
                "hybrid_branch": payload["hybrid_branch"],
                "ts": time.time(),
            }
        )
        return JSONResponse(payload)
    except ValueError:
        return error_response(400, "invalid_path", "Invalid upload path.")
    except Exception:  # noqa: BLE001
        logger.exception("upload_failed")
        return error_response(500, "upload_failed", "Upload failed.")
    finally:
        # Always delete temp upload dir after request
        if upload_dir is not None:
            try:
                shutil.rmtree(upload_dir, ignore_errors=True)
            except OSError:
                logger.warning("tmp_cleanup_failed path=%s", upload_dir)
        try:
            await file.close()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/history")
def api_history() -> Dict[str, Any]:
    items = list(HISTORY)[: config.HISTORY_CAP]
    return {"history": items, "cap": config.HISTORY_CAP}


@app.get("/api/findings")
def api_findings() -> Dict[str, Any]:
    return {"findings": parse_findings()}


@app.get("/api/banner")
def api_banner() -> Dict[str, Any]:
    return {"unverified": True, "items": _unverified_items()}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.FRONTEND_DIR / "index.html")


# Static assets (CSS/JS) — only under frontend/
if config.FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
    )
