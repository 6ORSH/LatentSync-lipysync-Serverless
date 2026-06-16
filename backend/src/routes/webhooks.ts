import { Hono } from "hono";
import { eq } from "drizzle-orm";
import type { Env } from "../types";
import { getDb } from "../db/client";
import { jobs as jobsTable } from "../db/schema";

export const webhooks = new Hono<{ Bindings: Env }>();

// Shape of the RunPod async result POSTed to our webhook (same as GET /status).
// `output` is whatever app.py returned.
interface RunpodWebhookBody {
  status?: string; // COMPLETED | FAILED | ...
  delayTime?: number; // ms spent queued before the GPU picked it up
  executionTime?: number; // ms of GPU compute
  output?: {
    status?: string; // "success" from app.py
    error?: string;
    results?: Array<{ outputs?: Array<{ output_video?: string }> }>;
  };
}

// POST /webhooks/runpod?secret=...&job=...
// RunPod calls this when a job finishes. We map it back to our job row via the
// `job` query param and validate the shared `secret`.
webhooks.post("/runpod", async (c) => {
  const secret = c.req.query("secret");
  const jobId = c.req.query("job");
  if (!jobId || secret !== c.env.WEBHOOK_SECRET) {
    return c.json({ error: "unauthorized" }, 401);
  }

  const body = await c.req.json<RunpodWebhookBody>().catch(() => null);
  if (!body) return c.json({ error: "bad payload" }, 400);

  const db = getDb(c.env);

  // Timing reported by RunPod (present on both success and failure).
  const timing = {
    completedAt: new Date(),
    runpodDelayMs: body.delayTime ?? null,
    runpodExecutionMs: body.executionTime ?? null,
  };

  if (body.status === "COMPLETED" && body.output?.status === "success") {
    const outputKey = body.output.results?.[0]?.outputs?.[0]?.output_video ?? null;
    await db
      .update(jobsTable)
      .set({ status: "completed", outputKey, ...timing })
      .where(eq(jobsTable.id, jobId));
  } else {
    const error = body.output?.error ?? `runpod status ${body.status ?? "unknown"}`;
    await db
      .update(jobsTable)
      .set({ status: "failed", error, ...timing })
      .where(eq(jobsTable.id, jobId));
  }

  return c.json({ ok: true });
});
