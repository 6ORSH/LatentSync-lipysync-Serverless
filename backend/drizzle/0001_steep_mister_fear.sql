ALTER TABLE "jobs" ADD COLUMN "completed_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "jobs" ADD COLUMN "runpod_delay_ms" integer;--> statement-breakpoint
ALTER TABLE "jobs" ADD COLUMN "runpod_execution_ms" integer;