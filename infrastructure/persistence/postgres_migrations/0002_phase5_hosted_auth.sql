ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS default_trusted_profile_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_organizations_default_trusted_profile'
    ) THEN
        ALTER TABLE organizations
        ADD CONSTRAINT fk_organizations_default_trusted_profile
        FOREIGN KEY (default_trusted_profile_id)
        REFERENCES trusted_profiles (trusted_profile_id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_subject ON users (auth_subject) WHERE auth_subject IS NOT NULL;

ALTER TABLE trusted_profile_drafts
ADD COLUMN IF NOT EXISTS draft_revision INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_trusted_profile_drafts_draft_revision'
    ) THEN
        ALTER TABLE trusted_profile_drafts
        ADD CONSTRAINT ck_trusted_profile_drafts_draft_revision
        CHECK (draft_revision > 0);
    END IF;
END $$;
