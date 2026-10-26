# ASSUMPTIONS — sandbox deepfake dashboard

**Mode:** sandbox / teacher-shareable demo. All inference claims are **UNVERIFIED**.

## Environment

| Fact | Status |
|------|--------|
| `/home/deepfake` | Not present on this cloud agent host |
| NVIDIA GPU / `nvidia-smi` | Not available |
| Real COCO v5 / face v6 checkpoints | Not available unless provided via env |
| Internet for heavy ML deps (torch/timm/opencv) | Not required; mock backend is default |

## Checkpoints

- **Documented expected prod path (COCO v5):** `/home/deepfake/deeptrace_data/coco_v5_effb4/coco_effb4_best.pt` — shown in Models panel; status `not found` unless file exists or `COCO_V5_CHECKPOINT` points to an existing file.
- **Face v6 path:** UNKNOWN on the original host. Sandbox documents expected placeholder `/home/deepfake/deeptrace_data/face_v6/face_v6_best.pt` and env override `FACE_V6_CHECKPOINT`. Status `not found` unless the file exists. Do not invent a discovered path.

## Hybrid decision rule (DEFAULT — NOT confirmed by owner)

Hybrid rule reconstructed as:

1. Compute mock (or real) scores `coco_score` and `face_score` in `[0, 1]` (higher = more likely FAKE).
2. `face_detected` is derived from a deterministic mock signal (or would come from a face detector in prod).
3. If `face_detected` is true and face model status is usable in prod: use **face branch** — compare `face_score` to `FACE_THRESHOLD` (default `0.55`).
4. Else: use **coco branch** — compare `coco_score` to `COCO_THRESHOLD` (default `0.50`).
5. Decision: score ≥ threshold → `FAKE`; score ≤ (1 − threshold) for coco or score < `FACE_REAL_FLOOR` (default `0.35`) for face → `REAL`; otherwise `UNCERTAIN`.
6. Confidence = absolute distance of chosen score from the decision boundary, clamped to `[0, 1]`.

**Hybrid rule reconstructed as above; NOT confirmed by owner.**

Defaults live in `backend/config.py` and are shown in the UI (branch + thresholds).

## Inference backend

- **Sandbox default:** `MockInferenceBackend` — deterministic scores derived from SHA-256 of the uploaded file bytes (first 8 hex digits → floats). Documented; not random; **not** real deepfake accuracy.
- **Optional real backend:** If `torch`, `timm`, and OpenCV import cleanly **and** checkpoint files exist, `TorchInferenceBackend` may be selected. On this host they are not required; mock is expected.
- Banner always lists: missing checkpoints, unverified hybrid rule, and mock inference when mock is active.

## Upload / temp paths

- Uploads stream to `./tmp/` under the repo root (equivalent intent to `dashboard/tmp` on the prod host). Per-request subdirs; deleted after the request.
- Max size default 50 MB (`MAX_UPLOAD_MB`). Allowed extensions: `.mp4`, `.mov`, `.avi`, `.mkv`.

## Limits (hard caps)

| Limit | Default | Env |
|-------|---------|-----|
| Max upload size | 50 MB | `MAX_UPLOAD_MB` |
| Analyze rate limit | 5/min per client | `ANALYZE_RATE_PER_MIN` |
| Global rate limit | 60/min per client | `GLOBAL_RATE_PER_MIN` |
| Inference timeout | 60 s | `INFERENCE_TIMEOUT_SEC` |
| History cap | 50 | `HISTORY_CAP` |
| Max frames / video | 300 | `MAX_FRAMES` |
| Max batch size | 8 | `MAX_BATCH_SIZE` |
| Max request wall time | 60 s | `INFERENCE_TIMEOUT_SEC` |

## API / UI

- Same surface as the original assignment: `/api/health`, `/api/models`, `/api/analyze`, `/api/history`, `/api/findings`, `/` → SPA.
- Error format: `{"error": {"code": "...", "message": "..."}}`.
- Bind **127.0.0.1:8001** only.
- No DB, Redis, CDN, or auth.

## Honesty

- This sandbox does **not** claim production deepfake detection quality.
- GPU metrics in health are `null` / N/A when `nvidia-smi` is unavailable.
- Security REVIEW lists checked items only; the app is not declared “secure.”
