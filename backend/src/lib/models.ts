import type { Env } from "../types";

// Models a user can choose. The `model` field on POST /jobs drives BOTH which
// RunPod endpoint the job goes to AND how much it costs — so adding a model is:
// add an entry here + set its RUNPOD_*_ENDPOINT_ID env var.
export type ModelId = "latentsync" | "keysync";

export interface ModelSpec {
  /** Credits charged for one job with this model. */
  cost: number;
  /** RunPod endpoint id for this model, resolved from env. */
  endpointId: (env: Env) => string | undefined;
}

// NOTE: `cost` values are placeholders — set to real per-job pricing. KeySync
// (SVD diffusion, ~24 GB of weights, heavier GPU) is priced above LatentSync.
export const MODELS: Record<ModelId, ModelSpec> = {
  latentsync: {
    cost: 10,
    endpointId: (env) => env.RUNPOD_ENDPOINT_ID,
  },
  keysync: {
    cost: 30,
    endpointId: (env) => env.RUNPOD_KEYSYNC_ENDPOINT_ID,
  },
};

export function isModelId(v: unknown): v is ModelId {
  return v === "latentsync" || v === "keysync";
}
