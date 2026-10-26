"""In-process rate limiting, upload validation, and safe path helpers."""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from backend import config


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def error_response(status: int, code: str, message: str, **headers: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=error_body(code, message),
        headers=headers or None,
    )


class RateLimiter:
    """Sliding-window per-client rate limiter. No Redis. Hard-capped deque length."""

    def __init__(self, max_per_minute: int, window_sec: float = 60.0) -> None:
        self.max_per_minute = max_per_minute
        self.window_sec = window_sec
        # Cap keys to avoid unbounded growth from unique spoofed clients
        self._max_clients = 10_000
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Use first hop only; treat as untrusted label for bucketing
            return forwarded.split(",")[0].strip()[:128]
        if request.client and request.client.host:
            return request.client.host[:128]
        return "unknown"

    def check(self, request: Request) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        key = self._client_key(request)
        now = time.monotonic()
        q = self._hits[key]
        # Evict expired — hard loop bound = current length
        max_iters = len(q)
        for _ in range(max_iters):
            if not q or now - q[0] < self.window_sec:
                break
            q.popleft()
        if len(q) >= self.max_per_minute:
            retry = max(1, int(self.window_sec - (now - q[0])) + 1)
            return False, retry
        q.append(now)
        # Bound deque size hard
        while len(q) > self.max_per_minute:
            q.popleft()
        # Bound number of tracked clients
        if len(self._hits) > self._max_clients:
            # Drop arbitrary oldest-ish keys (first inserted in CPython 3.7+)
            drop_n = len(self._hits) - self._max_clients
            for drop_key in list(self._hits.keys())[:drop_n]:
                del self._hits[drop_key]
        return True, 0


global_limiter = RateLimiter(config.GLOBAL_RATE_PER_MIN)
analyze_limiter = RateLimiter(config.ANALYZE_RATE_PER_MIN)

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    base = Path(name or "upload.bin").name  # strip directories
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip("._") or "upload.bin"
    if len(cleaned) > 200:
        cleaned = cleaned[:200]
    return cleaned


def extension_allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in config.ALLOWED_EXTENSIONS


def make_upload_dir() -> Path:
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    # Resolve to absolute; reject escape if somehow misconfigured
    root = config.TMP_DIR.resolve()
    req_dir = (root / f"req_{uuid.uuid4().hex}").resolve()
    if not str(req_dir).startswith(str(root)):
        raise RuntimeError("path_traversal_blocked")
    req_dir.mkdir(parents=True, exist_ok=False)
    return req_dir


def safe_join_upload(upload_dir: Path, filename: str) -> Path:
    root = upload_dir.resolve()
    target = (root / sanitize_filename(filename)).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("path_traversal")
    return target
