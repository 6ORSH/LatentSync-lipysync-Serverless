# Roadmap — LatentSync Lip-sync as a Product

Living document. We check progress against this. Tick items as they land.

## Architecture decisions (locked)

- **GPU inference:** RunPod Serverless (existing `app.py`). RunPod's `/run` queue +
  autoscaling workers replace any need for Celery/Redis for job dispatch.
- **Job completion:** RunPod **webhooks** call our backend — no polling worker.
- **Storage:** Cloudflare R2 (S3-compatible, $0 egress, global). Single bucket,
  prefix-per-user, lifecycle rules for retention.
- **Backend:** Cloudflare Worker (TypeScript + Hono) — "all on Cloudflare".
  Thin orchestration layer; RunPod does the heavy GPU work. Lives in `backend/`.
- **Database:** Postgres (Neon/PlanetScale) via **Hyperdrive** binding + Drizzle ORM.
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
- [x] Lifecycle rules: `inputs/` expire 1–3 days, `outputs/` expire 30 days
- [x] End-to-end test: stag run COMPLETED 2026-06-15 (image v7), result in R2 + presigned URL

Pipeline fix shipped alongside (v7): trim whisper_chunks to len(faces) so a
partial last inference window doesn't crash when face detection skips frames.

## Phase 2 — Backend API (Cloudflare Worker / TypeScript, in `backend/`)
Stack: Workers + Hono, R2 presign via aws4fetch, Postgres via Hyperdrive + Drizzle, JWT auth.

- **2a** scaffold ✅
  - [x] Worker + Hono, `GET /health`
  - [x] `POST /uploads` → presigned PUT URLs (video + audio) via aws4fetch
  - [x] Drizzle schema drafted (`users`, `jobs`); typecheck + dry-run build green
- **2b** database live
  - [x] Provision Neon Postgres + `wrangler hyperdrive create` (id wired in wrangler.toml)
  - [x] `db:generate` (initial migration committed); `getDb()` wired, Hyperdrive binding live
  - [x] `db:migrate` against Neon — verified: `GET /jobs/:id` returns 404 (table exists, Hyperdrive→Neon ok)
- **2c** jobs
  - [x] `POST /jobs` → RunPod `/run` (keys + webhook) → store job + runpod_id; `GET /jobs/:id`
  - [ ] Input validation: basic key checks done; size/duration/format limits TODO
- **2d** webhook
  - [x] `POST /webhooks/runpod` → verify secret → mark completed/failed + output key
- **2e** auth + history
  - [ ] Register/login, JWT middleware, scope jobs to user
  - [ ] `GET /jobs` history; `GET /jobs/:id/download` → presigned GET
- [x] Deploy worker (`wrangler deploy`) + secrets — live at latentsync-backend.foormanw.workers.dev
      (verified: /health, /uploads, R2 presigned PUT 200, Hyperdrive→Neon). Hyperdrive caching disabled.
- [ ] Live job E2E: POST /jobs with real files → webhook → completed + downloadUrl (user)

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
