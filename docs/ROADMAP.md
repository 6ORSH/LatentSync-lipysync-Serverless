# Roadmap — LatentSync Lip-sync as a Product

Living document. We check progress against this. Tick items as they land.

## Architecture decisions (locked)

- **GPU inference:** RunPod Serverless (existing `app.py`). RunPod's `/run` queue +
  autoscaling workers replace any need for Celery/Redis for job dispatch.
- **Job completion:** RunPod **webhooks** call our backend — no polling worker.
- **Storage:** Cloudflare R2 (S3-compatible, $0 egress, global). Single bucket,
  prefix-per-user, lifecycle rules for retention.
- **Backend:** FastAPI (Python — matches existing code, boto3, ffmpeg utils).
- **Database:** Postgres (users, jobs, balances).
- **Payments:** crypto first (global audience), cards (non-RU) later.
- **Clients:** web cabinet, then Telegram bot — both are just callers of the same backend API.
- **NOT using:** Celery, Redis-as-broker. (Redis maybe later for rate-limit/idempotency/cache only.)

Data flow:
```
client → backend: presigned PUT → upload input to R2
backend → RunPod /run (object keys + webhook url), charge/reserve balance
RunPod worker: GET inputs from R2 → inference → PUT result to R2
RunPod → backend webhook: job done
backend → client: presigned GET on result (history via DB + R2 keys)
```

---

## Phase 0 — Current state ✅
- [x] RunPod serverless worker runs LatentSync (`app.py`)
- [x] Image `6orsch/latentsync:v5`, checkpoints baked, no volume
- [x] Secrets via RunPod env (`secret: true`), no leaks in repo
- [x] Repo hygiene: `response.json` ignored, legacy handler marked deprecated

## Phase 1 — Storage foundation (R2)
Code side (done in repo):
- [x] Refactor `utils/s3.py` → R2: boto3 endpoint, `download_key`/`upload_key`/`presigned_get`
- [x] Gate arbitrary-URL download (`download_url`) to test/local smoke runs only (close SSRF in prod)
- [x] Output key scheme `outputs/{user_id}/{job_id}/result.mp4`; return key + presigned URL
- [x] Env routing → `R2_BUCKET` (stag/prod), `.runpod/hub.json` updated to R2 vars
- [x] `.gitignore` hardened (`*.env`), `stag.env.example` / `prod.env.example` templates

Cloudflare side (user, in dashboard) — needed before this can run:
- [x] Create R2 buckets `latentsync-prod` and `latentsync-stag`
- [x] Create R2 API token (Account API token, Object Read & Write); note Account ID
- [x] Set RunPod endpoint env: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `STAG_R2_BUCKET`, `PROD_R2_BUCKET`
- [ ] Lifecycle rules: `inputs/` expire 1–3 days, `outputs/` expire 30 days  ← still TODO
- [x] End-to-end test: stag run COMPLETED 2026-06-15 (image v7), result in R2 + presigned URL

Pipeline fix shipped alongside (v7): trim whisper_chunks to len(faces) so a
partial last inference window doesn't crash when face detection skips frames.

## Phase 2 — Backend API (the brain)
- [ ] FastAPI service skeleton + deploy target (Fly.io / Railway / VPS)
- [ ] Postgres schema: `users`, `jobs` (status, keys, cost, created_at, expires_at)
- [ ] Auth: register/login, JWT or API keys
- [ ] `POST /uploads` → presigned PUT URLs for video + audio
- [ ] `POST /jobs` → validate → call RunPod `/run` with keys + webhook → store job
- [ ] `POST /runpod/webhook` → mark job COMPLETED/FAILED, store output key
- [ ] `GET /jobs` → user history; `GET /jobs/{id}/download` → presigned GET
- [ ] Input validation + limits (duration, file size, format)

## Phase 3 — User cabinet (web)
- [ ] Frontend skeleton (framework TBD)
- [ ] Register / login
- [ ] Upload video + audio, submit generation
- [ ] Job progress (poll `GET /jobs/{id}` or websocket)
- [ ] History list + download, show "available N more days"

## Phase 4 — Telegram bot
- [ ] Bot as a thin client of the same backend API
- [ ] Link TG user → account (`users.tg_id`)
- [ ] Upload via TG → submit → deliver result link/file
- [ ] Notify on completion (reuse RunPod webhook → backend → bot push)

## Phase 5 — Payments
- [ ] Credits/balance model in `users`
- [ ] Reserve/charge before RunPod dispatch; refund on failure (idempotency → Redis here if needed)
- [ ] Crypto gateway integration (e.g. Cryptomus / NOWPayments)
- [ ] Pricing per generation (tie to RunPod cost + margin)
- [ ] Card payments (non-RU) — later

## Phase 6 — Production hardening
- [ ] Rate limiting per user (Redis)
- [ ] Monitoring + structured logging + error alerting
- [ ] RunPod job retry on transient failure
- [ ] Cost tracking / reconciliation
- [ ] Abuse prevention (quotas, content limits)
- [ ] Backups for Postgres
