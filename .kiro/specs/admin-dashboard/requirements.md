# Requirements Document

## Introduction

Real-time admin dashboard for the Fortress system, accessible from a browser during Early Production week. The dashboard provides at-a-glance monitoring of system health (all 5 services), today's activity counts, open items, recent conversations, open bugs, family members, and system uptime. It is served as a single self-contained HTML page from the FastAPI application with auto-refresh, dark theme, RTL Hebrew support, and mobile-friendly layout.

## Glossary

- **Dashboard_API**: The FastAPI endpoint at `GET /dashboard/data` that aggregates and returns all dashboard data as JSON.
- **Dashboard_Page**: The self-contained HTML file (embedded CSS/JS, no frameworks) served at `/dashboard` that renders the dashboard UI.
- **WAHA_Health_Checker**: The component that checks WAHA connectivity by calling `GET http://waha:3000/api/sessions`.
- **Static_File_Server**: The FastAPI static file mount at `/static` that serves the dashboard HTML and any related assets.
- **Startup_Script**: The shell scripts (`setup_mac_mini.sh`, `open_dashboard.sh`) that auto-open the dashboard in a browser on system startup.
- **Uptime_Tracker**: The component in `main.py` that records `APP_START_TIME` at startup and exposes `uptime_seconds` in the dashboard data.
- **Health_Status**: A string value representing service connectivity — one of `"connected"`, `"disconnected"`, `"no_key"`, or `"warning"`.
- **HEBREW_FALLBACK**: The hardcoded Hebrew fallback message string `"מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."` returned when all LLM providers fail.
- **Today_Window**: The time range from today 00:00 (local) to the current moment, used for filtering daily counts.

## Requirements

### Requirement 1: Dashboard Data API

**User Story:** As an admin, I want a single API endpoint that returns all dashboard data, so that the dashboard UI can fetch everything in one request.

#### Acceptance Criteria

1. WHEN a GET request is made to `/dashboard/data`, THE Dashboard_API SHALL return a JSON response with HTTP status 200.
2. THE Dashboard_API SHALL include a `health` object containing Health_Status values for each of the 5 services: database, Ollama, Bedrock, OpenRouter, and WAHA.
3. THE Dashboard_API SHALL include a `today` object containing integer counts for `conversations`, `tasks_created`, `bugs_reported`, and `errors` created within the Today_Window.
4. WHEN counting `errors` for today, THE Dashboard_API SHALL count Conversation records where the `message_out` field contains the HEBREW_FALLBACK string and `created_at` falls within the Today_Window.
5. THE Dashboard_API SHALL include an `open_items` object containing integer counts for `open_tasks` (tasks with status `"open"`) and `open_bugs` (bug_reports with status `"open"`).
6. THE Dashboard_API SHALL include a `recent_conversations` array containing the last 20 Conversation records ordered by `created_at` descending.
7. THE Dashboard_API SHALL include an `open_bugs` array containing all BugReport records where status is `"open"`, ordered by `created_at` descending.
8. THE Dashboard_API SHALL include a `family_members` array containing all active FamilyMember records.
9. THE Dashboard_API SHALL include a `system` object containing `version` (string), `uptime_seconds` (integer), and `app_start_time` (ISO 8601 string).


### Requirement 2: WAHA Health Check

**User Story:** As an admin, I want to see WAHA's connectivity status on the dashboard, so that I can verify the WhatsApp bridge is running.

#### Acceptance Criteria

1. WHEN checking WAHA health, THE WAHA_Health_Checker SHALL send a GET request to `{WAHA_API_URL}/api/sessions`.
2. WHEN the WAHA sessions endpoint returns HTTP 200, THE WAHA_Health_Checker SHALL report Health_Status as `"connected"`.
3. IF the WAHA sessions endpoint returns a non-200 status or a connection error occurs, THEN THE WAHA_Health_Checker SHALL report Health_Status as `"disconnected"`.

### Requirement 3: Dashboard HTML Page

**User Story:** As an admin, I want a self-contained HTML dashboard page with a dark theme, so that I can monitor the system from any browser without installing anything.

#### Acceptance Criteria

1. THE Dashboard_Page SHALL be a single HTML file with all CSS and JavaScript embedded inline, using no external frameworks or CDN dependencies.
2. THE Dashboard_Page SHALL auto-refresh the dashboard data every 30 seconds by calling the Dashboard_API.
3. THE Dashboard_Page SHALL use a dark theme with background color `#1a1a2e`, card background `#16213e`, accent color `#0f3460`, success color `#4ecca3`, warning color `#f0a500`, and error color `#e74c3c`.
4. THE Dashboard_Page SHALL support RTL (right-to-left) layout for Hebrew text content.
5. THE Dashboard_Page SHALL use a responsive layout that adapts to mobile screen widths (320px and above).
6. THE Dashboard_Page SHALL display six sections: System Health, Today statistics, Open Items, Open Bugs, Recent Activity, and Family Members.
7. THE Dashboard_Page SHALL display service health using status indicators: 🟢 for `"connected"`, 🟡 for `"warning"` or `"no_key"`, and 🔴 for `"disconnected"` or `"error"`.

### Requirement 4: Serve Static Files

**User Story:** As an admin, I want the dashboard accessible at a clean URL, so that I can bookmark and access it easily.

#### Acceptance Criteria

1. THE Static_File_Server SHALL mount a `/static` directory in the FastAPI application to serve static files.
2. WHEN a GET request is made to `/dashboard`, THE Static_File_Server SHALL serve the Dashboard_Page HTML file.

### Requirement 5: Auto-Open Dashboard on Startup

**User Story:** As an admin, I want the dashboard to open automatically when the system starts, so that I can immediately see system status after deployment.

#### Acceptance Criteria

1. THE Startup_Script SHALL create an `open_dashboard.sh` script that opens `http://localhost:8000/dashboard` in the default browser.
2. THE Startup_Script SHALL update `setup_mac_mini.sh` to invoke `open_dashboard.sh` after the Docker containers are running.

### Requirement 6: Uptime Tracking

**User Story:** As an admin, I want to see how long the application has been running, so that I can detect unexpected restarts.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE Uptime_Tracker SHALL record the current timestamp as `APP_START_TIME` in `main.py`.
2. WHEN the Dashboard_API is called, THE Uptime_Tracker SHALL calculate `uptime_seconds` as the integer difference between the current time and `APP_START_TIME`.
3. THE Uptime_Tracker SHALL include `APP_START_TIME` as an ISO 8601 formatted string in the `system` section of the Dashboard_API response.

### Requirement 7: Dashboard Tests

**User Story:** As a developer, I want comprehensive tests for the dashboard endpoints, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE test suite SHALL include a `test_dashboard.py` file covering the Dashboard_API endpoint.
2. THE test suite SHALL verify that `GET /dashboard/data` returns HTTP 200 with the expected JSON structure containing `health`, `today`, `open_items`, `recent_conversations`, `open_bugs`, `family_members`, and `system` keys.
3. THE test suite SHALL verify that the `today` counts query only records where `created_at` falls within the Today_Window.
4. THE test suite SHALL verify that the `errors` count correctly identifies Conversation records containing the HEBREW_FALLBACK string.
5. THE test suite SHALL verify that `recent_conversations` returns a maximum of 20 records ordered by `created_at` descending.
6. THE test suite SHALL verify that `open_bugs` returns only BugReport records with status `"open"`.
7. THE test suite SHALL verify that `uptime_seconds` is a non-negative integer.

### Requirement 8: README Roadmap Update

**User Story:** As a developer, I want the README to reflect the dashboard feature, so that the project documentation stays current.

#### Acceptance Criteria

1. THE README SHALL mention the admin dashboard in the STABLE-6 phase description within the roadmap table.
