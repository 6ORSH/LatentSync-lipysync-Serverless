# LatentSync Backend (Cloudflare Worker)

Thin orchestration API: issues R2 presigned URLs, submits jobs to RunPod,
receives completion webhooks, serves job history. See `../docs/ROADMAP.md` (Phase 2).

## Stack
- **Cloudflare Workers** + **Hono** (router)
- **R2** via presigned URLs (`aws4fetch`) — clients upload/download direct to R2
- **Postgres** via **Hyperdrive** + **Drizzle ORM**
- Auth: JWT (Slice 2e)

## Local dev
```bash
npm install
cp .dev.vars.example .dev.vars   # fill secrets
npm run dev                      # wrangler dev -> http://localhost:8787
```
Smoke test (no DB needed):
```bash
curl localhost:8787/health
curl -X POST localhost:8787/uploads
```

## Database (when provisioning)
1. Create a Postgres (Neon / PlanetScale Postgres).
2. `DATABASE_URL=postgres://... npm run db:generate && npm run db:migrate`
3. `wrangler hyperdrive create latentsync-db --connection-string="postgres://..."`
4. Paste the id into `wrangler.toml` `[[hyperdrive]]` and uncomment.

## Deploy
```bash
wrangler secret put R2_ACCESS_KEY_ID   # + R2_SECRET_ACCESS_KEY, RUNPOD_API_KEY, JWT_SECRET, WEBHOOK_SECRET
npm run deploy
```

## Status (build order)
- [x] 2a — scaffold: `/health`, `/uploads` (presigned PUT)
- [ ] 2b — Postgres schema live via Hyperdrive
- [ ] 2c — `/jobs` submit to RunPod + store
- [ ] 2d — `/webhooks/runpod` completion handling
- [ ] 2e — auth (JWT), scope jobs to user, `/jobs` history + download
