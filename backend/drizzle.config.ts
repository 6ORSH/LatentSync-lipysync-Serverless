import type { Config } from "drizzle-kit";

// drizzle-kit connects DIRECTLY to Postgres (not via Hyperdrive) to generate &
// apply migrations. Set DATABASE_URL to your Postgres connection string when
// running `npm run db:generate` / `db:migrate`.
export default {
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL ?? "" },
} satisfies Config;
