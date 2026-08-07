CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS "user" (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  image TEXT,
  role TEXT DEFAULT 'user',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_email ON "user" (email);

CREATE TABLE IF NOT EXISTS session (
  id TEXT PRIMARY KEY,
  expires_at TIMESTAMP NOT NULL,
  token TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  ip_address TEXT,
  user_agent TEXT,
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_user_id ON session (user_id);
CREATE INDEX IF NOT EXISTS idx_session_token ON session (token);

CREATE TABLE IF NOT EXISTS account (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
  access_token TEXT,
  refresh_token TEXT,
  id_token TEXT,
  access_token_expires_at TIMESTAMP,
  refresh_token_expires_at TIMESTAMP,
  scope TEXT,
  password TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_account_user_id ON account (user_id);

CREATE TABLE IF NOT EXISTS verification (
  id TEXT PRIMARY KEY,
  identifier TEXT NOT NULL,
  value TEXT NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_identifier ON verification (identifier);

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  repository TEXT,
  default_branch TEXT NOT NULL DEFAULT 'main',
  language TEXT NOT NULL DEFAULT 'latex',
  status TEXT NOT NULL DEFAULT 'active',
  is_public BOOLEAN NOT NULL DEFAULT FALSE,
  is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
  template TEXT NOT NULL DEFAULT 'IEEEtran',
  stars_count INTEGER NOT NULL DEFAULT 0,
  last_active_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects (user_id);

CREATE TABLE IF NOT EXISTS latex_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  raw_code TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_latex_documents_project_id ON latex_documents (project_id);
CREATE INDEX IF NOT EXISTS idx_latex_documents_file_path ON latex_documents (project_id, file_path);

CREATE TABLE IF NOT EXISTS latex_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1024)
);

CREATE INDEX IF NOT EXISTS idx_latex_chunks_project_id ON latex_chunks (project_id);
CREATE INDEX IF NOT EXISTS idx_latex_chunks_file_path ON latex_chunks (project_id, file_path);
CREATE INDEX IF NOT EXISTS idx_latex_chunks_embedding_hnsw ON latex_chunks
  USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION match_latex_chunks(
  query_embedding VECTOR(1024),
  match_project_id UUID,
  match_file_path TEXT DEFAULT NULL,
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 10
)
RETURNS TABLE (
  id UUID,
  project_id UUID,
  file_path TEXT,
  chunk_index INTEGER,
  content TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    lc.id,
    lc.project_id,
    lc.file_path,
    lc.chunk_index,
    lc.content,
    1 - (lc.embedding <=> query_embedding) AS similarity
  FROM latex_chunks lc
  WHERE lc.project_id = match_project_id
    AND (match_file_path IS NULL OR lc.file_path = match_file_path)
    AND 1 - (lc.embedding <=> query_embedding) > match_threshold
  ORDER BY lc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE TABLE IF NOT EXISTS project_members (
  id TEXT PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'editor',
  joined_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members (project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members (user_id);

CREATE TABLE IF NOT EXISTS project_invitations (
  id TEXT PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'editor',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_invitations_project_id ON project_invitations (project_id);

CREATE TABLE IF NOT EXISTS templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  file_extension TEXT NOT NULL DEFAULT 'cls',
  is_featured BOOLEAN NOT NULL DEFAULT FALSE,
  usage_count INTEGER NOT NULL DEFAULT 0,
  content TEXT
);

CREATE TABLE IF NOT EXISTS user_preferences (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES "user" (id) ON DELETE CASCADE,
  theme TEXT NOT NULL DEFAULT 'dark',
  email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
  security_alerts BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS editor_preferences (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES "user" (id) ON DELETE CASCADE,
  font_size INTEGER NOT NULL DEFAULT 14,
  tab_size INTEGER NOT NULL DEFAULT 2,
  word_wrap BOOLEAN NOT NULL DEFAULT TRUE,
  auto_compile BOOLEAN NOT NULL DEFAULT TRUE,
  engine TEXT NOT NULL DEFAULT 'pdfLaTeX',
  line_numbers BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'info',
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id);

CREATE TABLE IF NOT EXISTS recent_files (
  id TEXT PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'latex',
  last_opened_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS activity_logs (
  id TEXT PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  target TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_project_id ON activity_logs (project_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs (user_id);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE latex_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE latex_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE editor_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE recent_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY projects_owner_policy ON projects
  FOR ALL USING (user_id = current_setting('request.jwt.claim.sub', true));

CREATE POLICY latex_documents_owner_policy ON latex_documents
  FOR ALL USING (
    project_id IN (
      SELECT id FROM projects WHERE user_id = current_setting('request.jwt.claim.sub', true)
    )
  );

CREATE POLICY latex_chunks_owner_policy ON latex_chunks
  FOR ALL USING (
    project_id IN (
      SELECT id FROM projects WHERE user_id = current_setting('request.jwt.claim.sub', true)
    )
  );

CREATE POLICY project_members_owner_policy ON project_members
  FOR ALL USING (
    project_id IN (
      SELECT id FROM projects WHERE user_id = current_setting('request.jwt.claim.sub', true)
    )
    OR user_id = current_setting('request.jwt.claim.sub', true)
  );

CREATE POLICY project_invitations_owner_policy ON project_invitations
  FOR ALL USING (
    project_id IN (
      SELECT id FROM projects WHERE user_id = current_setting('request.jwt.claim.sub', true)
    )
  );

CREATE POLICY user_preferences_owner_policy ON user_preferences
  FOR ALL USING (user_id = current_setting('request.jwt.claim.sub', true));

CREATE POLICY editor_preferences_owner_policy ON editor_preferences
  FOR ALL USING (user_id = current_setting('request.jwt.claim.sub', true));

CREATE POLICY notifications_owner_policy ON notifications
  FOR ALL USING (user_id = current_setting('request.jwt.claim.sub', true));

CREATE POLICY recent_files_owner_policy ON recent_files
  FOR ALL USING (
    project_id IN (
      SELECT id FROM projects WHERE user_id = current_setting('request.jwt.claim.sub', true)
    )
  );

CREATE POLICY activity_logs_owner_policy ON activity_logs
  FOR ALL USING (user_id = current_setting('request.jwt.claim.sub', true));
