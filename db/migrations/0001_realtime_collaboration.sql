-- Real-Time Collaboration Schema Migration

CREATE TABLE IF NOT EXISTS "comments" (
  "id" text PRIMARY KEY,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "author_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "content" text NOT NULL,
  "resolved" boolean NOT NULL DEFAULT false,
  "created_at" timestamp NOT NULL DEFAULT now(),
  "updated_at" timestamp NOT NULL DEFAULT now()
);

-- Extend comments table
ALTER TABLE "comments" ADD COLUMN IF NOT EXISTS "document_id" text;
ALTER TABLE "comments" ADD COLUMN IF NOT EXISTS "parent_id" text;
ALTER TABLE "comments" ADD COLUMN IF NOT EXISTS "status" text NOT NULL DEFAULT 'open';
ALTER TABLE "comments" ADD COLUMN IF NOT EXISTS "mentioned_user_ids" jsonb DEFAULT '[]'::jsonb;

-- 1. Document Snapshots (Yjs CRDT persistence)
CREATE TABLE IF NOT EXISTS "document_snapshots" (
  "id" text PRIMARY KEY,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "document_id" text NOT NULL,
  "snapshot" text NOT NULL,
  "version" integer NOT NULL DEFAULT 1,
  "saved_by" text REFERENCES "user"("id") ON DELETE SET NULL,
  "created_at" timestamp NOT NULL DEFAULT now()
);

-- 2. Chat Messages
CREATE TABLE IF NOT EXISTS "chat_messages" (
  "id" text PRIMARY KEY,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "author_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "body" text NOT NULL,
  "mentioned_user_ids" jsonb DEFAULT '[]'::jsonb,
  "created_at" timestamp NOT NULL DEFAULT now(),
  "updated_at" timestamp NOT NULL DEFAULT now()
);

-- 3. Chat Read State
CREATE TABLE IF NOT EXISTS "chat_read_state" (
  "id" text PRIMARY KEY,
  "user_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "last_read_message_id" text,
  "updated_at" timestamp NOT NULL DEFAULT now(),
  CONSTRAINT "chat_read_state_user_project_unq" UNIQUE ("user_id", "project_id")
);

-- 4. Message Reactions
CREATE TABLE IF NOT EXISTS "message_reactions" (
  "id" text PRIMARY KEY,
  "message_id" text NOT NULL REFERENCES "chat_messages"("id") ON DELETE CASCADE,
  "user_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "emoji" text NOT NULL,
  "created_at" timestamp NOT NULL DEFAULT now(),
  CONSTRAINT "message_reactions_unq" UNIQUE ("message_id", "user_id", "emoji")
);
