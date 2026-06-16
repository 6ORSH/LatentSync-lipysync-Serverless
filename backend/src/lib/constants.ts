// Placeholder user until JWT auth lands (slice 2e). jobs.user_id is a FK to
// users.id, so we seed this fixed UUID on demand to allow pre-auth testing.
export const ANON_USER_ID = "00000000-0000-0000-0000-000000000000";

// Result retention — mirrors the R2 lifecycle rule on outputs/ (30 days).
export const RETENTION_MS = 30 * 24 * 60 * 60 * 1000;
