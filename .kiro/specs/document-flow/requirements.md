# Requirements Document

## Introduction

Fortress currently receives photos and files via WhatsApp but saves them with minimal metadata. This feature builds a proper document flow: structured storage with year/month directories, metadata extraction (filename, type, size, date), personality-template-based list and upload handlers, and document intent classification. No OCR — that comes in a future phase. This is about reliable storage and retrieval.

## Glossary

- **Document_Service**: The `src/services/documents.py` module responsible for processing, storing, and retrieving document records.
- **Workflow_Engine**: The `src/services/workflow_engine.py` LangGraph-based state machine that routes intents to handlers.
- **Personality_Module**: The `src/prompts/personality.py` module containing Hebrew templates and formatting functions for all user-facing text.
- **Intent_Detector**: The `src/services/intent_detector.py` module that classifies user messages into intent categories via keyword matching.
- **System_Prompts**: The `src/prompts/system_prompts.py` module containing LLM prompt templates including the unified classify-and-respond prompt.
- **Document**: An ORM model in `src/models/schema.py` representing a stored file with metadata fields (original_filename, doc_type, file_path, source, uploaded_by, created_at).
- **STORAGE_PATH**: The base directory for file storage, configured via environment variable in `src/config.py`.
- **Family_Member**: An ORM model representing a household member identified by phone number and role.

## Requirements

### Requirement 1: Structured Document Storage

**User Story:** As a family member, I want documents saved with proper metadata and organized directory structure, so that files are easy to find and manage.

#### Acceptance Criteria

1. WHEN a file is received for processing, THE Document_Service SHALL extract and store the following metadata: original_filename, file_path, source (set to "whatsapp"), doc_type (inferred from file extension), created_at, and uploaded_by.
2. WHEN inferring doc_type from a file extension, THE Document_Service SHALL map extensions as follows: .pdf → "document", .jpg/.jpeg/.png/.heic → "image", .doc/.docx → "document", .xls/.xlsx → "spreadsheet", all other extensions → "other".
3. WHEN storing a file, THE Document_Service SHALL use the path format `{STORAGE_PATH}/{year}/{month}/{uuid}_{original_filename}` where year and month are derived from the current date and uuid is a unique identifier.
4. WHEN the year or month subdirectory does not exist, THE Document_Service SHALL create the required directories before saving the file.
5. WHEN processing completes successfully, THE Document_Service SHALL return the created Document object with all metadata fields populated.
6. IF file processing fails, THEN THE Document_Service SHALL raise an exception with a descriptive error message.

### Requirement 2: Document List Handler with Personality Templates

**User Story:** As a family member, I want to ask "מה המסמכים שלי?" and get a formatted list of my recent documents, so that I can see what files are stored.

#### Acceptance Criteria

1. WHEN the intent is "list_documents" and permission is granted, THE Workflow_Engine SHALL query the 20 most recent documents for the requesting Family_Member ordered by creation date descending.
2. WHEN documents exist for the Family_Member, THE Workflow_Engine SHALL format the list using the Personality_Module document list templates and return the formatted result.
3. WHEN no documents exist for the Family_Member, THE Workflow_Engine SHALL return the document_list_empty template from the Personality_Module.
4. THE Personality_Module SHALL contain the following templates: document_list_header, document_list_empty, and document_list_item.
5. THE Personality_Module SHALL provide a `format_document_list(documents)` function that formats a list of Document objects into a Hebrew-formatted string using the document templates.
6. WHEN formatting a document list item, THE Personality_Module SHALL display an emoji based on doc_type: 📄 for "document", 🖼️ for "image", 📊 for "spreadsheet", 📎 for "other".

### Requirement 3: Upload Document Handler with Personality Templates

**User Story:** As a family member, I want to send a file via WhatsApp and receive a confirmation using the system's personality, so that the experience is consistent.

#### Acceptance Criteria

1. WHEN the intent is "upload_document" and a media file is present, THE Workflow_Engine SHALL save the file via Document_Service process_document and return the personality template confirmation: "שמרתי את הקובץ ✅ {filename}".
2. WHEN document saving fails, THE Workflow_Engine SHALL return the Personality_Module error_fallback template.
3. WHEN document saving fails, THE Workflow_Engine SHALL log the error with sufficient detail for debugging.

### Requirement 4: Document Intent Classification

**User Story:** As a family member, I want to ask about my documents in natural Hebrew and have the system understand my intent, so that I can retrieve document information conversationally.

#### Acceptance Criteria

1. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL include "list_documents" in the intent list with the Hebrew description "המשתמש רוצה לראות מסמכים ששמורים".
2. WHEN a user sends "מה המסמכים שלי?", THE Intent_Detector or unified LLM SHALL classify the intent as "list_documents".
3. WHEN a user sends "תראה מסמכים", THE Intent_Detector or unified LLM SHALL classify the intent as "list_documents".
4. WHEN a user sends "מסמכים" as a standalone keyword, THE Intent_Detector SHALL classify the intent as "list_documents".

### Requirement 5: Document Count in Greeting (Optional)

**User Story:** As a family member, I want my greeting to include a brief status summary, so that I know at a glance if there are pending items.

#### Acceptance Criteria

1. WHERE the greeting status summary feature is enabled, WHILE generating a greeting for a Family_Member who has pending items, THE Workflow_Engine SHALL include open task count and recent document count (last 7 days) in the greeting message.
2. WHERE the greeting status summary feature is enabled, THE Personality_Module SHALL format the summary as: "בוקר טוב {name}! ☀️ יש לך {task_count} משימות פתוחות ו-{doc_count} מסמכים חדשים."

### Requirement 6: Test Coverage for Document Flow

**User Story:** As a developer, I want comprehensive tests for the document flow, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE test suite SHALL include a test that process_document creates a Document record with correct metadata (original_filename, doc_type, source, file_path, uploaded_by).
2. THE test suite SHALL include a test that process_document creates year/month storage directories when they do not exist.
3. THE test suite SHALL include a test that process_document correctly infers doc_type from file extensions (.pdf → "document", .jpg → "image", .xlsx → "spreadsheet", .zip → "other").
4. THE test suite SHALL include a test that the list_documents handler returns a formatted list using personality templates.
5. THE test suite SHALL include a test that the list_documents handler returns the empty message template when no documents exist.
6. THE test suite SHALL include a test that the upload workflow creates a document and returns the personality confirmation template.
7. THE test suite SHALL include tests that the Personality_Module TEMPLATES dict contains document_list_header, document_list_empty keys.
8. THE test suite SHALL include a test that format_document_list with an empty list returns the document_list_empty template.
9. THE test suite SHALL include a test that format_document_list with multiple documents returns all document names.
10. THE test suite SHALL include a test that format_document_list shows correct emojis per doc_type (📄, 🖼️, 📊, 📎).
11. WHEN all new tests pass, THE existing 228 tests SHALL continue to pass without modification.

### Requirement 7: README Roadmap Update

**User Story:** As a developer, I want the README to reflect the current project status, so that the roadmap is accurate.

#### Acceptance Criteria

1. WHEN the document flow feature is complete, THE README roadmap table SHALL include a row: "STABLE-4 — Document Flow | ✅ Complete | Document storage, metadata, list/upload flow | {test_count}".
2. WHEN the document flow feature is complete, THE README "Current Version" line SHALL read "Phase STABLE-4".
