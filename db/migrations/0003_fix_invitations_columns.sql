-- Fix missing columns on project_invitations and notifications tables

-- project_invitations missing columns
ALTER TABLE "project_invitations" ADD COLUMN IF NOT EXISTS "sender_id" text REFERENCES "user"("id") ON DELETE CASCADE;
ALTER TABLE "project_invitations" ADD COLUMN IF NOT EXISTS "receiver_id" text REFERENCES "user"("id") ON DELETE CASCADE;
ALTER TABLE "project_invitations" ADD COLUMN IF NOT EXISTS "updated_at" timestamp NOT NULL DEFAULT now();

-- notifications missing/renamed columns
ALTER TABLE "notifications" ADD COLUMN IF NOT EXISTS "receiver_id" text REFERENCES "user"("id") ON DELETE CASCADE;
ALTER TABLE "notifications" ADD COLUMN IF NOT EXISTS "sender_id" text REFERENCES "user"("id") ON DELETE CASCADE;
ALTER TABLE "notifications" ADD COLUMN IF NOT EXISTS "project_id" text REFERENCES "projects"("id") ON DELETE CASCADE;
