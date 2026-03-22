BEGIN;

CREATE TABLE bug_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reported_by UUID REFERENCES family_members(id),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'fixed', 'wont_fix', 'duplicate')),
    priority TEXT DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'critical')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_bugs_status ON bug_reports(status);
CREATE INDEX idx_bugs_reporter ON bug_reports(reported_by);
CREATE INDEX idx_bugs_created ON bug_reports(created_at);

COMMIT;
