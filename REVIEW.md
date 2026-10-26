# Security REVIEW — sandbox deepfake dashboard

Honest checklist against the assignment. This app is **not** declared secure; only the items below were inspected.

| Severity | Where | What | How exploited | Fix |
|----------|-------|------|---------------|-----|
| Medium | `backend/security.py` RateLimiter | Client key from `X-Forwarded-For` / remote IP is spoofable when not behind a trusted proxy | Attacker rotates forged XFF values to bypass per-IP analyze limit (5/min) | Ignore XFF unless behind a trusted reverse proxy; or key only on `request.client.host` |
| Medium | `backend/app.py` `/api/analyze` | No authentication — any local client can submit videos | On a shared host, another user with local access floods analyze | Bind stays 127.0.0.1; add auth if ever exposed beyond localhost |
| Low | `backend/inference.py` MockInferenceBackend | Deterministic hash scores are predictable | Attacker crafts file bytes to force FAKE/REAL labels | Acceptable for sandbox; never ship mock as production signal |
| Low | `backend/app.py` HISTORY | In-memory history retains filenames from uploads (cap 50) | Local observer reads recent filenames via `/api/history` | Clear on shutdown (already); avoid sensitive filenames in demos |
| Low | `frontend/app.js` | Relies on `textContent` / `escapeHtml` for rendering | Stored XSS if escape regresses and API returns HTML | Keep escaping; add CSP header if hardened further |
| Info | `backend/app.py` `_gpu_info` | Subprocess `nvidia-smi` with fixed argv | N/A when binary missing; argv not user-controlled | Keep argv fixed; never pass user input |
| Info | Dependencies | Minimal FastAPI stack; torch not required | Supply-chain risk if adding heavy ML wheels later | Pin versions; run pip-audit when network available |
| Info | Upload temp dirs | Per-request dirs under `./tmp` deleted in `finally` | Crash mid-request could leave orphan dirs until manual cleanup | Periodic tmp sweeper with age cap (not implemented) |

## Checklist coverage

| Topic | Result |
|-------|--------|
| Injection (SQL/shell/HTML join) | No SQL/shell; frontend escapes HTML |
| Broken access control | Localhost-only bind; no auth (documented) |
| Weak auth | No auth by design in sandbox |
| Exposed secrets | None hardcoded |
| Unsafe file handling | Extension allowlist, size cap, stream to disk, path sanitize, delete after request |
| Unsafe loading (pickle/eval/exec) | Mock path only; torch backend refuses unverified load |
| SSRF | No outbound URL fetch from user input |
| DoS (limits/loops) | Rate limits, upload size, chunk loops bounded, history maxlen, inference timeout |
| Race conditions | Per-request tmp dirs with UUID; history deque not process-safe (single-worker assumption) |
| Weak crypto | Hash used only for mock scores, not security |
| Info leaks | Client errors omit stack traces; details logged server-side |
| Vulnerable deps | See build report — pip-audit / bandit / ruff / semgrep status |

## Tools

Run status is recorded in the build report after CI-local invocation. Missing tools are stated as “not run / not installed,” not skipped silently.
