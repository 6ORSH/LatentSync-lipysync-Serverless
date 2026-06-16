import { Hono } from "hono";
import type { Env } from "../types";
import { presignPut } from "../lib/r2";

export const uploads = new Hono<{ Bindings: Env }>();

// POST /uploads
// Returns presigned PUT URLs so the client uploads video + audio straight to R2.
// The returned jobId ties the input keys together; it is reused when the job is
// submitted (POST /jobs). user_id is "anon" until auth lands (Slice 2e).
uploads.post("/", async (c) => {
  const userId = "anon";
  const jobId = crypto.randomUUID();

  const videoKey = `inputs/${userId}/${jobId}/source.mp4`;
  const audioKey = `inputs/${userId}/${jobId}/audio.wav`;

  const [videoUrl, audioUrl] = await Promise.all([
    presignPut(c.env, videoKey),
    presignPut(c.env, audioKey),
  ]);

  return c.json({
    jobId,
    video: { key: videoKey, uploadUrl: videoUrl },
    audio: { key: audioKey, uploadUrl: audioUrl },
  });
});
