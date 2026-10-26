"""Inference backends: mock (default) and optional torch if deps + checkpoints exist."""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from backend import config
from backend.models_registry import any_checkpoint_ready

logger = logging.getLogger("dashboard.inference")


@dataclass
class AnalyzeResult:
    decision: str  # FAKE | REAL | UNCERTAIN
    confidence: float
    coco_score: float
    face_score: float
    face_detected: bool
    hybrid_branch: str
    thresholds: Dict[str, float]
    elapsed_sec: float
    inference_mode: str  # "mock" | "torch"
    filename: str
    unverified: bool
    notes: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InferenceBackend(ABC):
    mode: str

    @abstractmethod
    def analyze(self, video_path: Path, filename: str) -> AnalyzeResult:
        raise NotImplementedError


def _hybrid_decide(
    coco_score: float,
    face_score: float,
    face_detected: bool,
    filename: str,
    elapsed: float,
    mode: str,
    notes: list[str],
) -> AnalyzeResult:
    """DEFAULT hybrid rule — NOT confirmed by owner. See ASSUMPTIONS.md."""
    thresholds = {
        "coco_threshold": config.COCO_THRESHOLD,
        "face_threshold": config.FACE_THRESHOLD,
        "face_real_floor": config.FACE_REAL_FLOOR,
    }
    if face_detected:
        branch = "face"
        score = face_score
        if score >= config.FACE_THRESHOLD:
            decision = "FAKE"
            confidence = min(1.0, (score - config.FACE_THRESHOLD) / max(1e-6, 1.0 - config.FACE_THRESHOLD) + 0.5)
        elif score < config.FACE_REAL_FLOOR:
            decision = "REAL"
            confidence = min(1.0, (config.FACE_REAL_FLOOR - score) / max(1e-6, config.FACE_REAL_FLOOR) + 0.5)
        else:
            decision = "UNCERTAIN"
            confidence = 1.0 - abs(score - (config.FACE_THRESHOLD + config.FACE_REAL_FLOOR) / 2)
    else:
        branch = "coco"
        score = coco_score
        if score >= config.COCO_THRESHOLD:
            decision = "FAKE"
            confidence = min(1.0, 0.5 + (score - config.COCO_THRESHOLD))
        elif score <= (1.0 - config.COCO_THRESHOLD):
            decision = "REAL"
            confidence = min(1.0, 0.5 + ((1.0 - config.COCO_THRESHOLD) - score))
        else:
            decision = "UNCERTAIN"
            confidence = 1.0 - abs(score - config.COCO_THRESHOLD)

    confidence = max(0.0, min(1.0, round(confidence, 4)))
    return AnalyzeResult(
        decision=decision,
        confidence=confidence,
        coco_score=round(coco_score, 4),
        face_score=round(face_score, 4),
        face_detected=face_detected,
        hybrid_branch=branch,
        thresholds=thresholds,
        elapsed_sec=round(elapsed, 4),
        inference_mode=mode,
        filename=filename,
        unverified=True,
        notes=notes,
    )


class MockInferenceBackend(InferenceBackend):
    """Deterministic mock scores from file content hash. NOT real ML."""

    mode = "mock"

    def analyze(self, video_path: Path, filename: str) -> AnalyzeResult:
        t0 = time.perf_counter()
        # Stream hash — do not load entire huge files if somehow present;
        # still respect MAX_FRAMES conceptually by hashing in chunks with a bound.
        h = hashlib.sha256()
        chunk_limit = config.MAX_FRAMES * 64 * 1024  # soft read cap related to frame cap
        read_total = 0
        with video_path.open("rb") as f:
            # Hard loop bound: max number of chunks
            max_chunks = max(1, chunk_limit // 65536 + 1)
            for _ in range(max_chunks):
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
                read_total += len(chunk)
                if read_total >= chunk_limit:
                    break
        digest = h.hexdigest()
        # First 8 hex → coco; next 8 → face; next 2 → face_detected bit
        coco = int(digest[0:8], 16) / 0xFFFFFFFF
        face = int(digest[8:16], 16) / 0xFFFFFFFF
        face_detected = (int(digest[16:18], 16) % 2) == 1
        # Respect max batch size conceptually (mock "batches" of hash slices)
        _ = min(config.MAX_BATCH_SIZE, 8)
        elapsed = time.perf_counter() - t0
        notes = [
            "Mock inference: scores derived from SHA-256 of uploaded bytes (deterministic).",
            "NOT real deepfake accuracy. UNVERIFIED.",
            "Hybrid rule reconstructed as face-vs-coco branch; NOT confirmed by owner.",
        ]
        return _hybrid_decide(coco, face, face_detected, filename, elapsed, self.mode, notes)


class TorchInferenceBackend(InferenceBackend):
    """Placeholder real path — only used if torch/checkpoints available. Still UNVERIFIED."""

    mode = "torch"

    def __init__(self) -> None:
        # Import lazily; may fail
        import torch  # noqa: F401

        self._torch = torch

    def analyze(self, video_path: Path, filename: str) -> AnalyzeResult:
        # Without verified architecture + weights loading code from the owner host,
        # we refuse to invent torch.load of arbitrary checkpoints as "real" results.
        # Fall through semantics: raise so caller uses mock, or implement minimal stub.
        raise RuntimeError(
            "TorchInferenceBackend is not wired to verified prod architecture; "
            "sandbox refuses to claim real inference without owner-confirmed load path."
        )


def select_backend() -> InferenceBackend:
    if config.FORCE_MOCK:
        return MockInferenceBackend()
    if not any_checkpoint_ready():
        return MockInferenceBackend()
    try:
        import importlib

        for mod in ("torch", "timm", "cv2"):
            importlib.import_module(mod)
        return TorchInferenceBackend()
    except Exception as exc:  # noqa: BLE001 — sandbox: any import failure → mock
        logger.info("Falling back to mock inference: %s", exc)
        return MockInferenceBackend()


_BACKEND: Optional[InferenceBackend] = None


def get_backend() -> InferenceBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = select_backend()
    return _BACKEND


class InferenceTimeout(Exception):
    pass


def analyze_with_timeout(video_path: Path, filename: str) -> AnalyzeResult:
    backend = get_backend()
    timeout = config.INFERENCE_TIMEOUT_SEC
    # One-shot executor — hard timeout; no retry loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(backend.analyze, video_path, filename)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            fut.cancel()
            raise InferenceTimeout(f"inference exceeded {timeout}s") from exc
