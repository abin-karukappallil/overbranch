-- Missing core tables migration

-- Projects
CREATE TABLE IF NOT EXISTS "projects" (
  "id" text PRIMARY KEY,
  "owner_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "name" text NOT NULL,
  "description" text,
  "repository" text,
  "default_branch" text NOT NULL DEFAULT 'main.tex',
  "language" text NOT NULL DEFAULT 'latex',
  "status" text NOT NULL DEFAULT 'active',
  "is_public" boolean NOT NULL DEFAULT false,
  "is_favorite" boolean NOT NULL DEFAULT false,
  "template" text NOT NULL DEFAULT 'IEEEtran',
  "stars_count" integer NOT NULL DEFAULT 0,
  "last_active_at" timestamp NOT NULL DEFAULT now(),
  "created_at" timestamp NOT NULL DEFAULT now(),
  "updated_at" timestamp NOT NULL DEFAULT now()
);

-- Project Members
CREATE TABLE IF NOT EXISTS "project_members" (
  "id" text PRIMARY KEY,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "user_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "role" text NOT NULL DEFAULT 'Editor',
  "joined_at" timestamp NOT NULL DEFAULT now(),
  CONSTRAINT "project_members_project_id_user_id_unique" UNIQUE ("project_id", "user_id")
);

-- Project Invitations
CREATE TABLE IF NOT EXISTS "project_invitations" (
  "id" text PRIMARY KEY,
  "project_id" text NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
  "sender_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "receiver_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "email" text NOT NULL,
  "role" text NOT NULL DEFAULT 'Editor',
  "status" text NOT NULL DEFAULT 'Pending',
  "created_at" timestamp NOT NULL DEFAULT now(),
  "updated_at" timestamp NOT NULL DEFAULT now()
);

-- Notifications
CREATE TABLE IF NOT EXISTS "notifications" (
  "id" text PRIMARY KEY,
  "receiver_id" text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
  "sender_id" text REFERENCES "user"("id") ON DELETE CASCADE,
  "project_id" text REFERENCES "projects"("id") ON DELETE CASCADE,
  "type" text NOT NULL DEFAULT 'ProjectInvite',
  "title" text NOT NULL,
  "message" text NOT NULL,
  "is_read" boolean NOT NULL DEFAULT false,
  "created_at" timestamp NOT NULL DEFAULT now()
);
