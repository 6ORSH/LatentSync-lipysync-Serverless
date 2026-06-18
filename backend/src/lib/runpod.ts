import type { Env } from "../types";

export interface RunPodSubmitResult {
  id: string;
  status: string;
}

/**
 * Submit an async job to the RunPod serverless endpoint. RunPod queues it,
 * autoscales a GPU worker, and POSTs the result to `webhookUrl` when done.
 * `input` is the object placed under `{ "input": ... }` — it must match the
 * worker's contract in app.py (user_id, level, inp_meta[]).
 */
export async function submitJob(
  env: Env,
  input: unknown,
  webhookUrl: string,
  endpointId: string,
): Promise<RunPodSubmitResult> {
  const res = await fetch(`https://api.runpod.ai/v2/${endpointId}/run`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RUNPOD_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ input, webhook: webhookUrl }),
  });

  if (!res.ok) {
    throw new Error(`RunPod /run failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as RunPodSubmitResult;
}
