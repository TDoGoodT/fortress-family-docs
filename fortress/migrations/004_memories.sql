BEGIN;

-- Memories — things the system learns and remembers
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_member_id UUID REFERENCES family_members(id),
    content TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'preference', 'goal', 'fact', 'habit', 'context'
    )),
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'short',      -- 1 week
        'medium',     -- 3 months
        'long',       -- 1 year
        'permanent'   -- forever
    )),
    expires_at TIMESTAMPTZ,
    source TEXT CHECK (source IN (
        'conversation', 'document', 'manual', 'system'
    )),
    confidence DECIMAL DEFAULT 1.0,
    last_accessed_at TIMESTAMPTZ,
    access_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Things the system must NEVER remember
CREATE TABLE memory_exclusions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL,
    description TEXT,
    exclusion_type TEXT NOT NULL CHECK (exclusion_type IN (
        'keyword', 'category', 'regex'
    )),
    family_member_id UUID REFERENCES family_members(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Default exclusions — never store these
INSERT INTO memory_exclusions (pattern, exclusion_type, description) VALUES
    ('סיסמה', 'keyword', 'passwords in Hebrew'),
    ('password', 'keyword', 'passwords in English'),
    ('קוד', 'keyword', 'codes — PIN, gate, garden'),
    ('PIN', 'keyword', 'PIN codes'),
    ('תעודת זהות', 'keyword', 'ID numbers'),
    ('כרטיס אשראי', 'keyword', 'credit card numbers'),
    ('credit card', 'keyword', 'credit card numbers'),
    ('credentials', 'category', 'any credentials'),
    ('secret', 'keyword', 'secrets and keys');

-- Indexes
CREATE INDEX idx_memories_member ON memories(family_member_id);
CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_expires ON memories(expires_at);
CREATE INDEX idx_memories_active ON memories(is_active);
CREATE INDEX idx_exclusions_active ON memory_exclusions(is_active);
CREATE INDEX idx_exclusions_type ON memory_exclusions(exclusion_type);

COMMIT;
