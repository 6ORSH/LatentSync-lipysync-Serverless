import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import type { Env } from "../types";
import * as schema from "./schema";

// One connection per request — Workers isolates are short-lived; Hyperdrive
// pools the underlying Postgres connections. `fetch_types: false` avoids an
// extra round-trip on cold start.
export function getDb(env: Env) {
  const sql = postgres(env.HYPERDRIVE.connectionString, {
    max: 5,
    fetch_types: false,
  });
  return drizzle(sql, { schema });
}

export type Db = ReturnType<typeof getDb>;
