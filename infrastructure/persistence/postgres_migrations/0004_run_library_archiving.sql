ALTER TABLE processing_runs
ADD COLUMN IF NOT EXISTS archived_by_user_id TEXT REFERENCES users (user_id);

ALTER TABLE processing_runs
ADD COLUMN IF NOT EXISTS archived_at TEXT;
