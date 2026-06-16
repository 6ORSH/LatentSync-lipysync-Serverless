import { AwsClient } from "aws4fetch";
import type { Env } from "../types";

// Presigned URLs against the R2 S3-compatible endpoint. Clients upload/download
// directly to R2 (never streaming large video through the Worker), consistent
// with the RunPod worker's utils/s3.py.

function endpoint(env: Env): string {
  return `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`;
}

function client(env: Env): AwsClient {
  return new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    service: "s3",
    region: "auto",
  });
}

async function presign(
  env: Env,
  key: string,
  method: "PUT" | "GET",
  expiresIn: number,
): Promise<string> {
  const url = `${endpoint(env)}/${env.R2_BUCKET}/${key}?X-Amz-Expires=${expiresIn}`;
  const signed = await client(env).sign(url, {
    method,
    aws: { signQuery: true },
  });
  return signed.url;
}

/** Presigned PUT for a client to upload an input object (default 1h). */
export function presignPut(env: Env, key: string, expiresIn = 3600): Promise<string> {
  return presign(env, key, "PUT", expiresIn);
}

/** Presigned GET to deliver a result object (default 24h). */
export function presignGet(env: Env, key: string, expiresIn = 86400): Promise<string> {
  return presign(env, key, "GET", expiresIn);
}
