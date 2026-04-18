ALTER TABLE trusted_profile_drafts
ADD COLUMN IF NOT EXISTS draft_revision INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        WHERE ns.nspname = current_schema()
          AND rel.relname = 'trusted_profile_drafts'
          AND c.conname = 'ck_trusted_profile_drafts_draft_revision'
    ) THEN
        ALTER TABLE trusted_profile_drafts
        ADD CONSTRAINT ck_trusted_profile_drafts_draft_revision
        CHECK (draft_revision > 0);
    END IF;
END $$;
