# Implementation Plan: Document Flow

## Overview

Replace LLM-dispatched document handlers with deterministic personality templates, enhance `process_document()` with metadata extraction and organized storage, and add `format_document_list()` to the personality module. Implementation follows the existing patterns established for tasks (format_task_list, format_task_created).

## Tasks

- [x] 1. Update Document Service — improved process_document
  - [x] 1.1 Add `_infer_doc_type(filename)` helper to `fortress/src/services/documents.py`
    - Extension mapping: `.pdf`/`.doc`/`.docx` → `"document"`, `.jpg`/`.jpeg`/`.png`/`.heic` → `"image"`, `.xls`/`.xlsx` → `"spreadsheet"`, everything else → `"other"`
    - _Requirements: 1.2_
  - [x] 1.2 Enhance `process_document()` in `fortress/src/services/documents.py`
    - Extract `original_filename` from `file_path` using `os.path.basename()`
    - Infer `doc_type` via `_infer_doc_type()`
    - Generate storage path: `{STORAGE_PATH}/{year}/{month}/{uuid}_{original_filename}`
    - Create year/month directories with `os.makedirs(exist_ok=True)`
    - Copy file to storage path with `shutil.copy2()`
    - Save Document record with all metadata populated (`original_filename`, `doc_type`, `file_path` set to storage path)
    - Return the Document object
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Update Personality Module — document templates and format function
  - [x] 2.1 Add document templates to `TEMPLATES` dict in `fortress/src/prompts/personality.py`
    - Add `"document_list_header": "📁 המסמכים שלך:\n"`
    - Add `"document_list_empty": "אין מסמכים שמורים 📂"`
    - _Requirements: 2.4_
  - [x] 2.2 Add `_DOC_TYPE_EMOJI` mapping and `format_document_list()` function to `fortress/src/prompts/personality.py`
    - Follow the same pattern as `format_task_list()`
    - Empty list → return `TEMPLATES["document_list_empty"]`
    - Non-empty → header + numbered lines with doc_type emoji and filename
    - Use `getattr` with fallbacks for both ORM objects and dicts (same as `format_task_list`)
    - _Requirements: 2.5, 2.6_

- [x] 3. Update Workflow Engine — list_documents and upload_document handlers
  - [x] 3.1 Rewrite `_handle_upload_document` in `fortress/src/services/workflow_engine.py`
    - Remove LLM `dispatcher.dispatch()` call
    - On success: return `PERSONALITY_TEMPLATES["document_saved"].format(filename=doc.original_filename)`
    - On failure: log exception, return `PERSONALITY_TEMPLATES["error_fallback"]`
    - Import and use the returned Document object from `process_document()`
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 3.2 Rewrite `_handle_list_documents` in `fortress/src/services/workflow_engine.py`
    - Remove LLM `dispatcher.dispatch()` call
    - Query up to 20 most recent documents for the member, ordered by `created_at` desc
    - Import and call `format_document_list()` from personality module
    - Return the formatted string directly
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 4. Update System Prompts — document intent description
  - [x] 4.1 Add `list_documents` description to `UNIFIED_CLASSIFY_AND_RESPOND` in `fortress/src/prompts/system_prompts.py`
    - Add Hebrew description for list_documents intent: `"המשתמש רוצה לראות מסמכים ששמורים"`
    - Add after the existing `delete_task` description line
    - _Requirements: 4.1_

- [x] 5. Checkpoint — Verify core implementation
  - Ensure all existing 228 tests pass, ask the user if questions arise.

- [x] 6. Create tests for document flow
  - [x] 6.1 Update `REQUIRED_TEMPLATE_KEYS` in `fortress/tests/test_personality.py`
    - Add `"document_list_header"` and `"document_list_empty"` to the set
    - This is CRITICAL — the existing `test_templates_has_all_required_keys` uses exact set comparison and will fail without this update
    - _Requirements: 6.7, 6.11_
  - [x] 6.2 Add `format_document_list` import and tests to `fortress/tests/test_personality.py`
    - Import `format_document_list` from `src.prompts.personality`
    - Test empty list returns `TEMPLATES["document_list_empty"]`
    - Test multiple documents returns all filenames
    - Test correct emoji per doc_type (📄, 🖼️, 📊, 📎)
    - _Requirements: 6.8, 6.9, 6.10_
  - [x] 6.3 Create `fortress/tests/test_document_flow.py` with process_document tests
    - Test `process_document` creates Document record with correct `original_filename` extracted from path
    - Test `process_document` creates Document record with correct `doc_type` inferred from extension
    - Test `_infer_doc_type` extension mapping: `.pdf` → `"document"`, `.jpg` → `"image"`, `.xlsx` → `"spreadsheet"`, `.zip` → `"other"`
    - Test `process_document` creates year/month storage directories
    - Test storage path matches `{STORAGE_PATH}/{year}/{month}/{uuid}_{filename}` format
    - Mock filesystem operations (`os.makedirs`, `shutil.copy2`) — no real file I/O
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 6.4 Add handler tests to `fortress/tests/test_document_flow.py`
    - Test `_handle_list_documents` returns formatted list using personality templates (no LLM dispatch)
    - Test `_handle_list_documents` returns empty template when no documents exist
    - Test `_handle_upload_document` successful upload returns personality template confirmation with filename
    - Test `_handle_upload_document` failed upload returns `error_fallback` template
    - Mock DB using `MagicMock(spec=Session)` (existing pattern from conftest)
    - _Requirements: 6.4, 6.5, 6.6_
  - [x] 6.5 Add intent classification tests to `fortress/tests/test_document_flow.py`
    - Test `"מה המסמכים שלי?"` → `list_documents` (contains "מסמכים" substring)
    - Test `"תראה מסמכים"` → `list_documents` (contains "מסמכים" substring)
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 7. Update README
  - [x] 7.1 Update `README.md` roadmap and version
    - Change "Current Version" line to "Phase STABLE-4"
    - Add row to roadmap table: `STABLE-4 — Document Flow | ✅ Complete | Document storage, metadata, list/upload personality templates | {test_count}`
    - Update test count in the status section
    - _Requirements: 7.1, 7.2_

- [-] 8. Final checkpoint — All tests pass and push
  - Run full test suite, ensure all existing 228 tests plus new tests pass.
  - Push to origin main.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- No schema changes needed — Document model already has all required fields
- Requirement 5 (greeting with status) is skipped per user request — it's optional
- No property-based tests — unit tests only
- `REQUIRED_TEMPLATE_KEYS` in test_personality.py MUST be updated in task 6.1 before running tests, or existing tests will break
- Both `_handle_upload_document` and `_handle_list_documents` currently use LLM dispatch — they need to be changed to use personality templates
- `format_document_list()` follows the same pattern as `format_task_list()`
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
