import { pgTable, uuid, text, timestamp, integer, bigint, index } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: text("email").unique(),
  passwordHash: text("password_hash"),
  tgId: bigint("tg_id", { mode: "number" }).unique(),
  balance: integer("balance").notNull().default(0), // credits
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const jobs = pgTable(
  "jobs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id),
    status: text("status").notNull().default("queued"), // queued|running|completed|failed
    inputVideoKey: text("input_video_key").notNull(),
    inputAudioKey: text("input_audio_key").notNull(),
    outputKey: text("output_key"),
    runpodId: text("runpod_id"),
    cost: integer("cost").notNull().default(0),
    error: text("error"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
  },
  (t) => ({
    userIdx: index("jobs_user_created_idx").on(t.userId, t.createdAt),
  }),
);

export type User = typeof users.$inferSelect;
export type Job = typeof jobs.$inferSelect;
