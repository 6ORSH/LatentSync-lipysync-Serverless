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

  const jobId = body.jobId ?? crypto.randomUUID();

  // Matches app.py contract. level "stag" -> STAG_R2_BUCKET on the worker.
  const input = {
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

  const webhookUrl =
    `${c.env.PUBLIC_BASE_URL}/webhooks/runpod` +
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

  return c.json({
    jobId: job.id,
    status: job.status,
    error: job.error,
    downloadUrl,
    createdAt: job.createdAt,
    expiresAt: job.expiresAt,
  });
});
