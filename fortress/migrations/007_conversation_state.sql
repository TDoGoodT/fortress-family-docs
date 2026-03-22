BEGIN;

CREATE TABLE conversation_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_member_id UUID NOT NULL REFERENCES family_members(id) UNIQUE,
    last_intent TEXT,
    last_entity_type TEXT,
    last_entity_id UUID,
    last_action TEXT,
    pending_confirmation BOOLEAN DEFAULT false,
    pending_action JSONB,
    context JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_conv_state_member ON conversation_state(family_member_id);

COMMIT;
