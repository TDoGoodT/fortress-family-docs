# fortress.ingestion.pipeline-architecture.v3

## Version Metadata
- Document ID: fortress.ingestion.pipeline-architecture
- Version: v3
- Layer: ingestion
- Status: ACTIVE
- Canonical: Yes
- Supersedes: fortress.ingestion.pipeline-architecture.v2
- Depends On:
  - fortress.core.database-blueprint.v1
  - fortress.core.event-ledger.v1
  - fortress.security.zone-model.v2
  - fortress.project.implementation-roadmap.v2
  - fortress.project.dependency-model.v2
  - fortress.project.version-governance.v1

---

## Delta From v2

- Introduces fully canonical Idempotency Primitives section.
- Defines required hash columns per ingestion table.
- Defines deterministic hash input rules.
- Defines required unique constraints for record-level idempotency.
- Defines run-level vs record-level dedupe behavior.
- Defines required operational indexes.
- No changes to stage model, zone placement, ledger mapping, or sequencing rules.

---

# 2) Idempotency Primitives (Canonical)

## 2.1 Hash Algorithm

All ingestion hashes use:

- Algorithm: SHA-256
- Storage type: `bytea` (32 raw digest bytes)
- Display encoding (non-storage only): `encode(hash, 'hex')` lowercase

Hash storage MUST NOT use text.

---

## 2.2 Canonicalization Rules (Hash Input Determinism)

When hashing JSON payloads:

- UTF-8 encoding
- Object keys sorted lexicographically
- No insignificant whitespace
- Numbers rendered per JSON standard
- `null` preserved
- No floating formatting differences

When hashing raw bytes:

- Use exact stored byte sequence
- No transformations

---

## 2.3 Required Hash Columns Per Table

### ingestion.raw_object
- `content_sha256 bytea NOT NULL`

Definition:
- If `raw_payload` (bytea) is present → sha256(raw_payload)
- Else → sha256(canonical_json(raw_payload_json))

Idempotency anchor: content-level dedupe

---

### ingestion.raw_record
- `record_sha256 bytea NOT NULL`

Definition:
sha256(
  concat_bytes(
 ource_id,
    record_type,
    canonical_json(record_payload),
    coalesce(record_external_id, ''),
    record_seq
  )
)

---

### ingestion.normalized_record
- `normalized_sha256 bytea NOT NULL`

Definition:
sha256(
  concat_bytes(
    source_id,
    canonical_record_type,
    schema_version,
    canonical_json(normalized_payload)
  )
)

---

### ingestion.canonical_handoff_request
- `handoff_sha256 bytea NOT NULL`

Definition:
sha256(
  concat_bytes(
    target_entity_type,
    coalesce(target_entity_id, ''),
    canonical_json(handoff_payload)
  )
)

---

### ingestion.error
- `error_fingerprint_sha256 bytea NOT NULL`

Definition:
sha256(
  concat_bytes(
    stage,
    subject_type,
    coalesce(subject_id, ''),
    error_class,
    error_code,
    stable_error_root(details)
  )
)

`stable_error_root(details)` must include only deterministic fields per error_class:
- transport: http_status, provider_error_code, timeout_ms
- parsing: parser_name, parser_version, failing_field
- auth: auth_scope, auth_reason
- storage: errno
- validation: schema_version, rule_id

---

## 2.4 Unique Constraints (Idempotency Enforcement)

### ingestion.source
UNIQUE (source_type, source_key)

---

### ingestion.raw_object
UNIQUE (source_id, object_locator, content_sha256)

---

### ingestion.raw_record
UNIQUE (raw_object_id, record_seq)
UNIQUE (source_id, record_sha256)

---

### ingestion.normalized_record
UNIQUE (raw_record_id, schema_version)
UNIQUE (source_id, normalized_sha256, schema_version)

---

### ingestion.canonical_handoff_request
UNIQUE (normalized_record_id)
UNIQUE (handoff_sha256)

---

### ingestion.error
UNIQUE (run_id, stage, subject_type, subject_id, attempt)
UNIQUE (run_id, error_fingerprint_sha256, attempt)

---

## 2.5 Deterministic Dedupe Behavior

Run-level retries are allowed.

Idempotency is enforced at record-level and handoff-level only.

Rules:

If inserting `raw_record` violates UNIQUE(source_id, record_sha256):
→ Treat as duplicate
→ Do not create new normalized_record
→ Emit duplicate evf inserting `normalized_record` violates UNIQUE(source_id, normalized_sha256, schema_version):
→ Treat as duplicate
→ Do not create new handoff request
→ Emit duplicate event

If inserting `canonical_handoff_request` violates UNIQUE(handoff_sha256):
→ Treat as duplicate
→ Do not create new request
→ Emit duplicate event

---

## 2.6 Required Indexes

Add btree indexes for:

- raw_object(content_sha256)
- raw_record(record_sha256)
- normalized_record(normalized_sha256)
- canonical_handoff_request(handoff_sha256)
- error(error_fingerprint_sha256)

Operational indexes:

- run(source_id, created_at DESC)
- run_state(run_id, state_seq)
- error(run_id, stage)
- canonical_handoff_request(run_id)
