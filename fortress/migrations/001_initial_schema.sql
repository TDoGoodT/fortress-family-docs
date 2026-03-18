-- Fortress 2.0 Initial Schema
-- 6 core tables, clean and simple

BEGIN;

-- Family members identified by phone number
CREATE TABLE family_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('parent', 'child', 'grandparent', 'other')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Role-based permissions
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    can_read BOOLEAN DEFAULT false,
    can_write BOOLEAN DEFAULT false,
    UNIQUE(role, resource_type)
);

-- Default permissions
INSERT INTO permissions (role, resource_type, can_read, can_write) VALUES
    ('parent', 'finance', true, true),
    ('parent', 'documents', true, true),
    ('parent', 'tasks', true, true),
    ('child', 'finance', false, false),
    ('child', 'documents', true, false),
    ('child', 'tasks', true, true),
    ('grandparent', 'finance', false, false),
    ('grandparent', 'documents', true, false),
    ('grandparent', 'tasks', true, false);

-- Documents (invoices, contracts, receipts, etc.)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    uploaded_by UUID REFERENCES family_members(id),
    file_path TEXT NOT NULL,
    original_filename TEXT,
    doc_type TEXT,
    vendor TEXT,
    amount DECIMAL,
    currency TEXT DEFAULT 'ILS',
    doc_date DATE,
    description TEXT,
    ai_summary TEXT,
    raw_text TEXT,
    source TEXT NOT NULL CHECK (source IN ('whatsapp', 'email', 'filesystem', 'manual')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Financial transactions derived from documents
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    category TEXT,
    amount DECIMAL NOT NULL,
    currency TEXT DEFAULT 'ILS',
    direction TEXT NOT NULL CHECK (direction IN ('income', 'expense')),
    transaction_date DATE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Simple audit log
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES family_members(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id UUID,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- WhatsApp conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_member_id UUID REFERENCES family_members(id),
    message_in TEXT,
    message_out TEXT,
    intent TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX idx_family_members_phone ON family_members(phone);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_vendor ON documents(vendor);
CREATE INDEX idx_documents_created_at ON documents(created_at);
CREATE INDEX idx_documents_source ON documents(source);
CREATE INDEX idx_transactions_category ON transactions(category);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_direction ON transactions(direction);
CREATE INDEX idx_audit_log_actor ON audit_log(actor_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);
CREATE INDEX idx_conversations_member ON conversations(family_member_id);
CREATE INDEX idx_conversations_created ON conversations(created_at);

COMMIT;
