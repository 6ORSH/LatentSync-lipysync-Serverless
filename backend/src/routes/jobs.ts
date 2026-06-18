import { Hono } from "hono";
import { eq } from "drizzle-orm";
import type { Env } from "../types";
import { getDb } from "../db/client";
import { jobs as jobsTable, users } from "../db/schema";
import { submitJob } from "../lib/runpod";
import { presignGet } from "../lib/r2";
import { ANON_USER_ID, RETENTION_MS } from "../lib/constants";

export const jobs = new Hono<{ Bindings: Env }>();

interface CreateJobBody {
  jobId?: string;
  videoKey?: string;
  audioKey?: string;
  cc?: boolean;
  inferenceSteps?: number; // quality/speed; omitted -> worker default (20)
  guidanceScale?: number; // lip-sync strength; omitted -> worker default (1.5)
}

// POST /jobs — submit a lip-sync job.
// Expects the input keys from a prior POST /uploads (client has since uploaded
// the files to R2). Submits to RunPod and records the job.
jobs.post("/", async (c) => {
  const userId = ANON_USER_ID; // until auth (slice 2e)
  const body = await c.req.json<CreateJobBody>().catch(() => null);

  if (!body?.videoKey || !body?.audioKey) {
    return c.json({ error: "videoKey and audioKey are required" }, 400);
  }
  if (!body.videoKey.startsWith("inputs/") || !body.audioKey.startsWith("inputs/")) {
    return c.json({ error: "keys must be under inputs/" }, 400);
  }

  // Pre-flight: both inputs must already exist in R2. Catches the common
  // "submitted before the upload finished" case instantly — a clear 400 instead
  // of spinning up a GPU worker that fails on a missing object.
  const [videoObj, audioObj] = await Promise.all([
    c.env.BUCKET.head(body.videoKey),
    c.env.BUCKET.head(body.audioKey),
  ]);
  const missing = [videoObj ? null : body.videoKey, audioObj ? null : body.audioKey].filter(
    (k): k is string => k !== null,
  );
  if (missing.length > 0) {
    return c.json({ error: "input not uploaded", missing }, 400);
  }

  const jobId = body.jobId ?? crypto.randomUUID();

  // Matches app.py contract. level "stag" -> STAG_R2_BUCKET on the worker.
  const input: Record<string, unknown> = {
    user_id: "anon",
    level: "stag",
    inp_meta: [
      {
        ref_video_path: body.videoKey,
        ref_audio_meta: [{ audio_path: body.audioKey }],
        cc: Boolean(body.cc),
      },
    ],
  };

  // Optional quality/speed knobs (omitted -> worker defaults 20 / 1.5).
  if (body.inferenceSteps !== undefined) {
    if (!Number.isInteger(body.inferenceSteps) || body.inferenceSteps < 1 || body.inferenceSteps > 50) {
      return c.json({ error: "inferenceSteps must be an integer between 1 and 50" }, 400);
    }
    input.inference_steps = body.inferenceSteps;
  }
  if (body.guidanceScale !== undefined) {
    if (typeof body.guidanceScale !== "number" || body.guidanceScale < 1 || body.guidanceScale > 5) {
      return c.json({ error: "guidanceScale must be a number between 1.0 and 5.0" }, 400);
    }
    input.guidance_scale = body.guidanceScale;
  }

  // Derive the callback base from the incoming request origin so the webhook
  // always points at wherever this Worker is actually reachable — robust to a
  // missing/misconfigured PUBLIC_BASE_URL. PUBLIC_BASE_URL overrides only when
  // explicitly set to an https URL (e.g. a custom domain).
  const override = c.env.PUBLIC_BASE_URL;
  const base = override && override.startsWith("https://") ? override : new URL(c.req.url).origin;
  const webhookUrl =
    `${base}/webhooks/runpod` +
    `?secret=${encodeURIComponent(c.env.WEBHOOK_SECRET)}&job=${jobId}`;

  const rp = await submitJob(c.env, input, webhookUrl);

  const db = getDb(c.env);
  await db.insert(users).values({ id: userId }).onConflictDoNothing();
  await db.insert(jobsTable).values({
    id: jobId,
    userId,
    status: "queued",
    inputVideoKey: body.videoKey,
    inputAudioKey: body.audioKey,
    runpodId: rp.id,
    expiresAt: new Date(Date.now() + RETENTION_MS),
  });

  return c.json({ jobId, status: "queued", runpodId: rp.id });
});

// GET /jobs/:id — status + (when ready) a presigned download URL.
jobs.get("/:id", async (c) => {
  const id = c.req.param("id");
  const db = getDb(c.env);
  const [job] = await db.select().from(jobsTable).where(eq(jobsTable.id, id)).limit(1);

  if (!job) return c.json({ error: "not found" }, 404);

  let downloadUrl: string | null = null;
  if (job.status === "completed" && job.outputKey) {
    downloadUrl = await presignGet(c.env, job.outputKey);
  }

  // End-to-end wall time from submit (createdAt) to webhook receipt (completedAt).
  const totalSeconds = job.completedAt
    ? (job.completedAt.getTime() - job.createdAt.getTime()) / 1000
    : null;

  return c.json({
    jobId: job.id,
    status: job.status,
    error: job.error,
    downloadUrl,
    createdAt: job.createdAt,
    completedAt: job.completedAt,
    timing: {
      totalSeconds,
      runpodDelayMs: job.runpodDelayMs,
      runpodExecutionMs: job.runpodExecutionMs,
    },
    expiresAt: job.expiresAt,
  });
});
