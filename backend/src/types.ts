/** Worker bindings & environment. Mirrors wrangler.toml + secrets. */
export interface Env {
  // --- R2 (Cloudflare) ---
  R2_ACCOUNT_ID: string;
  R2_ACCESS_KEY_ID: string; // secret
  R2_SECRET_ACCESS_KEY: string; // secret
  R2_BUCKET: string; // active bucket for this environment (matches the RunPod `level`)

  // --- RunPod ---
  RUNPOD_API_KEY: string; // secret
  RUNPOD_ENDPOINT_ID: string; // LatentSync endpoint
  RUNPOD_KEYSYNC_ENDPOINT_ID: string; // KeySync endpoint (set when that model is deployed)

  // --- Auth / webhooks ---
  JWT_SECRET: string; // secret
  WEBHOOK_SECRET: string; // secret — validates RunPod -> backend callbacks
  PUBLIC_BASE_URL: string; // base URL the worker is reachable at (for webhook callback)

  // --- Bindings ---
  BUCKET: R2Bucket;
  HYPERDRIVE: Hyperdrive;
}
