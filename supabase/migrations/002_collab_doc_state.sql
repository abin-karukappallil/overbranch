-- 002_collab_doc_state.sql
-- Durable CRDT state for realtime collaborative editing.
--
-- Apply with either:
--     psql "$DATABASE_URL" -f supabase/migrations/002_collab_doc_state.sql
--     npm run db:push          (from db/schema.ts -> collabDocState)
--
-- There is deliberately no drizzle/ migration for this: drizzle/meta is still
-- at the 0000 baseline while db/schema.ts has grown a dozen tables since, so
-- `drizzle-kit generate` would emit all of them at once. This file is
-- idempotent and safe to run on an existing database.
--
-- The *text* of a document continues to live in `latex_documents`; this table
-- holds the Yjs update blob (base64) for the project's collaboration room.
--
-- Why the blob is needed at all: rebuilding a room by inserting the plain text
-- into a fresh Y.Doc gives that text a brand-new CRDT identity. A client that
-- reconnects after a server restart still holds the *old* identity, and the
-- merge of the two would duplicate the entire document. Re-applying this blob
-- restores the original identity, so the merge is a no-op.
--
-- One row per project: the room's Y.Doc contains every open file as a separate
-- Y.Text root (`file:<path>`), plus a `meta` map recording what has been
-- persisted. base64 TEXT rather than BYTEA because the backend reaches this
-- table through the Supabase REST client.

CREATE TABLE IF NOT EXISTS collab_doc_state (
  project_id UUID PRIMARY KEY REFERENCES projects (id) ON DELETE CASCADE,
  state_b64 TEXT NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collab_doc_state_updated_at ON collab_doc_state (updated_at);

ALTER TABLE collab_doc_state ENABLE ROW LEVEL SECURITY;

-- Only the service role (the FastAPI backend) touches this table; browsers
-- never read it, so no permissive policy is created for anon/authenticated.
