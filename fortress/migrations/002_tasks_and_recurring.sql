BEGIN;

-- Recurring patterns table (must be created before tasks, which references it)
CREATE TABLE recurring_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    assigned_to UUID REFERENCES family_members(id),
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
    day_of_month INT,
    month_of_year INT,
    next_due_date DATE NOT NULL,
    auto_create_days_before INT DEFAULT 7,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_recurring_next_due ON recurring_patterns(next_due_date);
CREATE INDEX idx_recurring_active ON recurring_patterns(is_active);
CREATE INDEX idx_recurring_frequency ON recurring_patterns(frequency);

-- Tasks table
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'archived')),
    assigned_to UUID REFERENCES family_members(id),
    created_by UUID REFERENCES family_members(id),
    source_document_id UUID REFERENCES documents(id),
    due_date DATE,
    category TEXT,
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    recurring_pattern_id UUID REFERENCES recurring_patterns(id),
    completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
CREATE INDEX idx_tasks_category ON tasks(category);
CREATE INDEX idx_tasks_recurring ON tasks(recurring_pattern_id);
CREATE INDEX idx_tasks_source_doc ON tasks(source_document_id);

COMMIT;
