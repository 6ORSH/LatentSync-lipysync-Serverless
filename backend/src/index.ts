import { Hono } from "hono";
import type { Env } from "./types";
import { uploads } from "./routes/uploads";
import { jobs } from "./routes/jobs";
import { webhooks } from "./routes/webhooks";

const app = new Hono<{ Bindings: Env }>();

app.get("/health", (c) => c.json({ status: "ok", service: "latentsync-backend" }));

app.route("/uploads", uploads);
app.route("/jobs", jobs);
app.route("/webhooks", webhooks);

// TODO (slice 2e): /auth (register/login, JWT), scope /jobs to the authed user,
// GET /jobs history listing.

export default app;
