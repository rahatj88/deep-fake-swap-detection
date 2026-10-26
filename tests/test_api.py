"""API tests for the sandbox deepfake dashboard."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.app import HISTORY, app
from backend.inference import MockInferenceBackend
from backend.security import analyze_limiter, global_limiter, sanitize_filename


@pytest.fixture(autouse=True)
def _clean_history_and_limits():
    HISTORY.clear()
    global_limiter._hits.clear()
    analyze_limiter._hits.clear()
    yield
    HISTORY.clear()
    global_limiter._hits.clear()
    analyze_limiter._hits.clear()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "gpu" in data
    assert "unverified" in data
    assert isinstance(data["unverified"], list)
    assert data["inference_mode"] == "mock"
    assert data["bind"] == "127.0.0.1:8001"


def test_models_show_documented_paths_not_found(client: TestClient):
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    models = data["models"]
    assert len(models) >= 2
    names = {m["name"] for m in models}
    assert any("COCO" in n for n in names)
    assert any("Face" in n for n in names)
    # Without real files, expect not found
    for m in models:
        if "COCO" in m["name"] or "Face" in m["name"]:
            # env override could make ready; default sandbox: not found
            assert m["status"] in {"not found", "ready"}
            assert m["documented_expected"] is True
    assert "hybrid_defaults" in data
    assert "coco_threshold" in data["hybrid_defaults"]


def test_index_serves_html(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "UNVERIFIED" in r.text
    assert "text/html" in r.headers.get("content-type", "")


def test_analyze_mock_deterministic(client: TestClient):
    payload = b"ftypisom" + b"\x00" * 64 + b"sandbox-demo-bytes"
    files = {"file": ("clip.mp4", io.BytesIO(payload), "video/mp4")}
    r1 = client.post("/api/analyze", files=files)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["decision"] in {"FAKE", "REAL", "UNCERTAIN"}
    assert d1["inference_mode"] == "mock"
    assert d1["unverified"] is True
    assert "hybrid_branch" in d1
    assert d1["hybrid_branch"] in {"face", "coco"}
    assert "thresholds" in d1

    files2 = {"file": ("clip.mp4", io.BytesIO(payload), "video/mp4")}
    r2 = client.post("/api/analyze", files=files2)
    d2 = r2.json()
    assert d1["coco_score"] == d2["coco_score"]
    assert d1["face_score"] == d2["face_score"]
    assert d1["decision"] == d2["decision"]


def test_analyze_rejects_bad_extension(client: TestClient):
    files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = client.post("/api/analyze", files=files)
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "invalid_type"


def test_analyze_rejects_oversize(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0.001)
    files = {"file": ("big.mp4", io.BytesIO(b"x" * 2048), "video/mp4")}
    r = client.post("/api/analyze", files=files)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_history_cap_and_order(client: TestClient):
    for i in range(3):
        content = f"vid-{i}-".encode() + b"\x00" * 32
        files = {"file": (f"c{i}.mp4", io.BytesIO(content), "video/mp4")}
        assert client.post("/api/analyze", files=files).status_code == 200
    hist = client.get("/api/history").json()["history"]
    assert len(hist) == 3
    assert len(hist) <= config.HISTORY_CAP
    # Most recent first
    assert hist[0]["filename"] == "c2.mp4"
    assert hist[-1]["filename"] == "c0.mp4"


def test_findings_parses_review(client: TestClient):
    r = client.get("/api/findings")
    assert r.status_code == 200
    findings = r.json()["findings"]
    assert isinstance(findings, list)
    # REVIEW.md ships with a table
    assert len(findings) >= 1
    assert "severity" in findings[0]
    assert "where" in findings[0]


def test_sanitize_filename_blocks_traversal():
    assert ".." not in sanitize_filename("../../etc/passwd")
    assert sanitize_filename("/tmp/a.mp4") == "a.mp4"
    assert "/" not in sanitize_filename("a/b/c.mp4")


def test_mock_backend_notes():
    backend = MockInferenceBackend()
    tmp = Path(config.TMP_DIR)
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "unit.mp4"
    path.write_bytes(b"unit-test-bytes")
    try:
        result = backend.analyze(path, "unit.mp4")
        assert result.inference_mode == "mock"
        assert any("NOT real" in n for n in result.notes)
    finally:
        path.unlink(missing_ok=True)


def test_error_format_on_empty(client: TestClient):
    files = {"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")}
    r = client.post("/api/analyze", files=files)
    assert r.status_code == 400
    body = r.json()
    assert set(body["error"].keys()) == {"code", "message"}


def test_banner_endpoint(client: TestClient):
    r = client.get("/api/banner")
    assert r.status_code == 200
    data = r.json()
    assert data["unverified"] is True
    joined = " ".join(data["items"])
    assert re.search(r"mock|Hybrid|checkpoint|Sandbox", joined, re.I)
