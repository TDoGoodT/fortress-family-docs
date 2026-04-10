# Document Cabinet Follow-up (Lightweight)

This change adds a lightweight organization and retrieval layer on top of the existing document intake pipeline.

## Scope
- Uses existing `documents.tags` JSONB and `documents.review_state`.
- Keeps raw files immutable.
- Adds deterministic query filters and WhatsApp command handling in `DocumentSkill`.
- No new infrastructure (no vector DB/graph DB/agent framework).

## Implemented
1. Deterministic tag normalization and deduplication (`lowercase`, strip `#`).
2. Auto-tags generated from existing pipeline metadata (`doc_type`, `vendor`, `review_state`, year, selected fact types).
3. Manual tagging commands in `DocumentSkill` (`add/remove/show/search by tag`).
4. Recent documents feed (`latest N`, capped to 20, default 5).
5. Predefined saved-search style views via deterministic filters:
   - `active_contracts`
   - `insurance_documents`
   - `recent_invoices`
   - `needs_review`
6. Search filter support expanded for `review_state` + `tag` (with existing type/vendor/keyword/recent).

## Notes
- Tag writes merge with existing tags while preserving order and uniqueness.
- Commands resolve “this document” using existing conversation-state-aware resolution.
- Existing ingestion flow remains intact; tagging is an additive step after review-state assignment.
