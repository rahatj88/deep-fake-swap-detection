# Deepfake / Face-swap Detection Dashboard — Sandbox

Teacher-shareable **sandbox** of the video deepfake detection API + single-page dashboard.

- Binds **127.0.0.1:8001** only
- Default inference is **mock** (deterministic SHA-256 scores) — **UNVERIFIED**, not real deepfake accuracy
- No `/home/deepfake`, GPU, or checkpoints required
- Hybrid rule defaults are reconstructed and **NOT confirmed by owner** (see `ASSUMPTIONS.md`)

## Quick start

```bash
cd /path/to/this/repo

# Preferred (needs python3-venv / ensurepip):
python3 -m venv .venv

# If ensurepip is missing (common on minimal images), bootstrap pip instead:
#   python3 -m venv --without-pip .venv
#   curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
#   .venv/bin/python /tmp/get-pip.py

source .venv/bin/activate
pip install -r requirements.txt

# Run API + UI (bind localhost:8001 only)
PYTHONPATH=. uvicorn backend.app:app --host 127.0.0.1 --port 8001

# Or:
PYTHONPATH=. python -m backend.app
```

Open [http://127.0.0.1:8001/](http://127.0.0.1:8001/).

## Tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest -q
```

## Smoke test (analyze)

```bash
# tiny synthetic “video” with an allowed extension
printf 'ftypisomfakevideo' > /tmp/sample.mp4
curl -s -F "file=@/tmp/sample.mp4;type=video/mp4" http://127.0.0.1:8001/api/analyze | python3 -m json.tool
```

Expect JSON with `decision` (`FAKE`/`REAL`/`UNCERTAIN`), `confidence`, `coco_score`, `face_score`, `hybrid_branch`, `inference_mode: "mock"`, and `unverified: true`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | GPU (or N/A), disk, CPU, uptime, version, unverified list |
| GET | `/api/models` | Checkpoint registry + hybrid defaults + limits |
| POST | `/api/analyze` | Multipart video upload → decision |
| GET | `/api/history` | Last ≤50 in-memory results |
| GET | `/api/findings` | Parsed `REVIEW.md` table |
| GET | `/` | Dashboard SPA |

Errors use `{"error":{"code","message"}}` with appropriate status (413, 429, 504, …).

## Optional real checkpoints

If you have weight files:

```bash
export COCO_V5_CHECKPOINT=/path/to/coco_effb4_best.pt
export FACE_V6_CHECKPOINT=/path/to/face_v6.pt
export FORCE_MOCK=0
```

Even then, the sandbox **refuses** to claim torch inference without an owner-verified load path; mock remains the honest default (`FORCE_MOCK=1`).

## Layout

```
ASSUMPTIONS.md
README.md
REVIEW.md
backend/
  app.py
  security.py
  inference.py
  models_registry.py
  config.py
frontend/
  index.html
  app.js
  styles.css
tests/
  test_api.py
requirements.txt
```

## Honesty

Do not treat dashboard labels as production deepfake detection. Missing checkpoints, unverified hybrid rule, and mock inference are always banner-flagged.
