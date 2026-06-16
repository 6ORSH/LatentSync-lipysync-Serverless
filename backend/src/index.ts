import { Hono } from "hono";
import type { Env } from "./types";
import { uploads } from "./routes/uploads";

const app = new Hono<{ Bindings: Env }>();

app.get("/health", (c) => c.json({ status: "ok", service: "latentsync-backend" }));

app.route("/uploads", uploads);

// TODO (next slices): /jobs (RunPod submit), /webhooks/runpod, /auth, /jobs history

export default app;
