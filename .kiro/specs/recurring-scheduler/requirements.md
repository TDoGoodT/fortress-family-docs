# Requirements Document

## Introduction

Fortress has a `recurring_patterns` table and a `recurring.py` service with `generate_tasks_from_due_patterns()`, but nothing runs it automatically. This feature adds an automated daily scheduler that generates tasks from due recurring patterns, sends WhatsApp notifications to assigned family members, and provides WhatsApp-based management commands for creating, listing, and deleting recurring patterns. The scheduler runs daily at 07:00 via APScheduler embedded in the FastAPI application.

## Glossary

- **Scheduler_Service**: The `src/services/scheduler.py` module responsible for orchestrating the daily recurring task generation cycle
- **Scheduler_Router**: The `src/routers/scheduler.py` FastAPI router exposing scheduler trigger and status endpoints
- **Recurring_Service**: The existing `src/services/recurring.py` module that manages recurring patterns and generates tasks
- **WhatsApp_Client**: The existing `src/services/whatsapp_client.py` module that sends messages via WAHA API
- **Intent_Detector**: The existing `src/services/intent_detector.py` module that classifies incoming WhatsApp messages into intents
- **Routing_Policy**: The existing `src/services/routing_policy.py` module that maps intents to sensitivity tiers and provider routes
- **Workflow_Engine**: The existing `src/services/workflow_engine.py` LangGraph-based workflow that processes WhatsApp messages
- **Unified_Handler**: The existing `src/services/unified_handler.py` module that performs single-LLM classify+respond calls
- **Personality_Module**: The existing `src/prompts/personality.py` module containing Hebrew templates and formatting functions
- **APScheduler**: The `apscheduler` library used to schedule the daily cron job within the FastAPI process
- **Due_Pattern**: A RecurringPattern whose `next_due_date - auto_create_days_before <= today`
- **Notification**: A WhatsApp text message sent to a family member informing them of an auto-created task
- **Scheduler_Run_Record**: An in-memory or persisted record of the last scheduler execution including timestamp and task count

## Requirements

### Requirement 1: Daily Scheduler Service

**User Story:** As a family admin, I want recurring tasks to be generated automatically every day, so that no one has to manually trigger task creation from recurring patterns.

#### Acceptance Criteria

1. WHEN `run_daily_schedule` is invoked, THE Scheduler_Service SHALL call `recurring.get_due_patterns(db)` to retrieve all active Due_Patterns.
2. WHEN Due_Patterns are found, THE Scheduler_Service SHALL call `recurring.generate_tasks_from_due_patterns(db)` to create tasks and advance each pattern's `next_due_date`.
3. WHEN tasks are created, THE Scheduler_Service SHALL return a list of dictionaries containing each created task's `id`, `title`, `due_date`, and the assigned family member's `phone` number.
4. WHEN no Due_Patterns are found, THE Scheduler_Service SHALL return an empty list and log that no patterns were due.
5. THE Scheduler_Service SHALL log every action: the number of due patterns found, each task created (title and assigned member), and the total count of created tasks.
6. IF an error occurs during task generation for a single pattern, THEN THE Scheduler_Service SHALL log the error and continue processing remaining patterns.

### Requirement 2: Scheduler API Endpoints

**User Story:** As a system operator, I want HTTP endpoints to trigger the scheduler and check its status, so that I can invoke it from cron or monitoring tools.

#### Acceptance Criteria

1. WHEN a POST request is received at `/scheduler/run`, THE Scheduler_Router SHALL invoke `run_daily_schedule` and return a JSON response with `tasks_created` count and `notifications_sent` count.
2. WHEN a GET request is received at `/scheduler/status`, THE Scheduler_Router SHALL return a JSON response with `last_run` timestamp and `tasks_created_last_run` count.
3. WHEN the scheduler has not yet run, THE Scheduler_Router SHALL return `last_run` as `null` and `tasks_created_last_run` as `0`.
4. THE Scheduler_Router SHALL be registered in `main.py` and accessible without authentication (internal Docker network only).

### Requirement 3: WhatsApp Notifications for Auto-Created Tasks

**User Story:** As a family member, I want to receive a WhatsApp notification when a recurring task is created for me, so that I know about upcoming responsibilities.

#### Acceptance Criteria

1. WHEN the Scheduler_Service creates a task with an assigned family member, THE Scheduler_Service SHALL send a WhatsApp Notification to that member's phone number using `whatsapp_client.send_text_message()`.
2. THE Notification message SHALL use the `reminder_new_task` Personality_Module template formatted as: "📋 תזכורת: {title}\n📅 עד {due_date}\nנוצר אוטומטית מתבנית חוזרת."
3. WHEN the Scheduler_Service completes a run, THE Scheduler_Service SHALL send a summary Notification to the admin phone using the `scheduler_summary` Personality_Module template.
4. IF a Notification fails to send, THEN THE Scheduler_Service SHALL log the error and continue processing remaining notifications without raising an exception.
5. THE Scheduler_Service SHALL track and return the count of successfully sent notifications.

### Requirement 4: Personality Templates for Recurring Features

**User Story:** As a family member, I want all recurring-related messages to use consistent Hebrew personality templates, so that the experience feels natural and cohesive.

#### Acceptance Criteria

1. THE Personality_Module SHALL include a `reminder_new_task` template with the format: "📋 תזכורת: {title}\n📅 עד {due_date}\nנוצר אוטומטית מתבנית חוזרת."
2. THE Personality_Module SHALL include a `scheduler_summary` template with the format: "🔄 סיכום יומי: נוצרו {count} משימות מתבניות חוזרות."
3. THE Personality_Module SHALL include a `recurring_list_header` template: "🔄 התזכורות החוזרות שלך:\n"
4. THE Personality_Module SHALL include a `recurring_list_empty` template: "אין תזכורות חוזרות פעילות 📭"
5. THE Personality_Module SHALL include a `recurring_list_item` template: "{index}. {title} — {frequency} (הבא: {next_due_date})"
6. THE Personality_Module SHALL include a `recurring_created` template: "יצרתי תזכורת חוזרת: {title} ✅\nתדירות: {frequency}\nהבא: {next_due_date}"
7. THE Personality_Module SHALL include a `recurring_deleted` template: "תזכורת חוזרת בוטלה: {title} ✅"
8. THE Personality_Module SHALL include a `recurring_not_found` template: "לא מצאתי את התזכורת הזו 🤷"
9. THE Personality_Module SHALL include a `format_recurring_list` function that formats a list of RecurringPattern objects using the above templates.

### Requirement 5: Intent Detection for Recurring Management

**User Story:** As a family member, I want to manage recurring patterns by sending WhatsApp messages with Hebrew or English keywords, so that I can create, list, and delete recurring reminders conversationally.

#### Acceptance Criteria

1. WHEN a message contains "תזכורות" or "חוזרות" or "recurring", THE Intent_Detector SHALL classify the intent as `list_recurring`.
2. WHEN a message starts with "תזכורת חדשה:" or "recurring:", THE Intent_Detector SHALL classify the intent as `create_recurring`.
3. WHEN a message contains "מחק תזכורת" or "בטל תזכורת", THE Intent_Detector SHALL classify the intent as `delete_recurring`.
4. THE Intent_Detector SHALL register `list_recurring`, `create_recurring`, and `delete_recurring` in the `INTENTS` dictionary with `model_tier` set to `"local"`.
5. THE Routing_Policy SHALL map `list_recurring`, `create_recurring`, and `delete_recurring` intents to `"medium"` sensitivity level.

### Requirement 6: Recurring Pattern Workflow Handlers

**User Story:** As a family member, I want the system to handle my recurring management requests through the existing workflow, so that permissions, memory, and conversation logging all work consistently.

#### Acceptance Criteria

1. WHEN the intent is `list_recurring`, THE Workflow_Engine SHALL query all active recurring patterns for the current member and return a formatted list using `format_recurring_list`.
2. WHEN the intent is `create_recurring` and the message contains a title and frequency, THE Workflow_Engine SHALL create a new RecurringPattern with the parsed title, frequency, and a calculated `next_due_date`, then return a confirmation using the `recurring_created` template.
3. WHEN the intent is `delete_recurring`, THE Workflow_Engine SHALL identify the target pattern by number or title match, deactivate the pattern using `recurring.deactivate_pattern()`, and return a confirmation using the `recurring_deleted` template.
4. IF the target pattern for deletion is not found, THEN THE Workflow_Engine SHALL return the `recurring_not_found` template.
5. THE Workflow_Engine SHALL add `list_recurring`, `create_recurring`, and `delete_recurring` to the `_PERMISSION_MAP` with `("tasks", "write")` for create/delete and `("tasks", "read")` for list.
6. THE Workflow_Engine SHALL add handler functions for the three recurring intents to the `_ACTION_HANDLERS` dispatch table.

### Requirement 7: Unified Handler Integration

**User Story:** As a developer, I want the unified LLM handler to recognize recurring management intents, so that ambiguous messages can be routed to recurring workflows via LLM classification.

#### Acceptance Criteria

1. THE Unified_Handler SHALL include `list_recurring`, `create_recurring`, and `delete_recurring` in the `VALID_INTENTS` set (via Intent_Detector INTENTS registration).
2. WHEN the LLM classifies a message as `create_recurring`, THE Unified_Handler SHALL extract `recurring_data` from the JSON response containing `title`, `frequency`, and optional `assigned_to`.
3. THE system prompt `UNIFIED_CLASSIFY_AND_RESPOND` SHALL be updated to include recurring intent descriptions and the `recurring_data` JSON format.

### Requirement 8: APScheduler Integration

**User Story:** As a system operator, I want the scheduler to run automatically at 07:00 daily without requiring an external cron container, so that the deployment remains simple.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE application SHALL initialize an APScheduler `AsyncIOScheduler` with a CronTrigger set to run at 07:00 daily.
2. WHEN the scheduled job fires, THE application SHALL call the POST `/scheduler/run` endpoint logic internally.
3. WHEN the FastAPI application shuts down, THE application SHALL gracefully shut down the APScheduler instance.
4. THE `requirements.txt` SHALL include `apscheduler==3.10.4` as a dependency.

### Requirement 9: Shell Script for Manual Scheduler Trigger

**User Story:** As a system operator, I want a shell script to manually trigger the scheduler, so that I can test or force a run outside the daily schedule.

#### Acceptance Criteria

1. THE `scripts/run_scheduler.sh` script SHALL send a POST request to `http://localhost:8000/scheduler/run`.
2. THE `scripts/run_scheduler.sh` script SHALL print the JSON response from the scheduler endpoint.
3. THE `scripts/run_scheduler.sh` script SHALL be executable (chmod +x).

### Requirement 10: Test Coverage

**User Story:** As a developer, I want comprehensive tests for the scheduler and recurring management features, so that regressions are caught early.

#### Acceptance Criteria

1. THE test suite SHALL include `tests/test_scheduler.py` with tests for: run with no due patterns returns empty, run with due patterns creates tasks, `next_due_date` advances after task creation, notifications are sent for created tasks, and notification failure does not crash the scheduler.
2. THE test suite SHALL include `tests/test_recurring_management.py` with tests for: `list_recurring` intent detection, `create_recurring` intent detection, `delete_recurring` intent detection, list handler returns formatted patterns, create handler creates a pattern, and delete handler deactivates a pattern.
3. THE test suite SHALL include tests in `tests/test_personality.py` for: recurring templates exist, `format_recurring_list` with patterns, and `format_recurring_list` with empty list.
4. THE test suite SHALL maintain all 254 existing tests passing after the changes.

### Requirement 11: README Roadmap Update

**User Story:** As a developer, I want the README to reflect the current project status, so that the roadmap is accurate.

#### Acceptance Criteria

1. WHEN the feature is complete, THE README SHALL update the roadmap table to include a `STABLE-5 — Recurring Scheduler` row with status `✅ Complete` and the updated test count.
2. THE README SHALL update the "Current Version" text to `Phase STABLE-5`.
