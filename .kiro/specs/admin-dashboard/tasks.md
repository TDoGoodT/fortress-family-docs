# Implementation Plan: Admin Dashboard

## Overview

Add a browser-based admin dashboard to Fortress. The implementation follows the design document: a new FastAPI router with JSON data endpoint, a self-contained HTML page, shell scripts for auto-open, and updates to main.py for static file serving and uptime tracking. All tests follow existing patterns from conftest.py.

## Tasks

- [x] 1. Create static directory and dashboard router
  - [x] 1.1 Create `fortress/src/static/` directory with an empty `.gitkeep` file
    - This directory will hold `dashboard.html` and any future static assets
    - _Requirements: 4.1_

  - [x] 1.2 Create `fortress/src/routers/dashboard.py` with `/dashboard/data` endpoint
    - Import existing health check pattern from `health.py` (OllamaClient, BedrockClient, OpenRouterClient, test_connection)
    - Import `WAHA_API_URL` from `src.config` and `OPENROUTER_API_KEY` from `src.config`
    - Import ORM models: Conversation, Task, BugReport, FamilyMember from `src.models.schema`
    - Implement `check_waha_health()` async function using `httpx.AsyncClient` with 5s timeout against `{WAHA_API_URL}/api/sessions`
    - Implement `GET /dashboard/data` endpoint with `db: Session = Depends(get_db)`
    - Run all 5 health checks (DB via `test_connection()`, Ollama, Bedrock, OpenRouter, WAHA)
    - Query today's counts: conversations, tasks_created, bugs_reported, errors (HEBREW_FALLBACK in message_out)
    - Query open_items: open_tasks count, open_bugs count
    - Query recent_conversations: last 20 ordered by created_at desc, joined with FamilyMember for name
    - Query open_bugs: all with status "open", ordered by created_at desc, joined with FamilyMember for reporter name
    - Query family_members: all active
    - Calculate uptime from imported `APP_START_TIME`
    - Return full JSON response matching the design schema
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 6.2, 6.3_

  - [x] 1.3 Add `GET /dashboard` endpoint to dashboard router
    - Use `FileResponse` to serve `src/static/dashboard.html`
    - _Requirements: 4.2_

- [x] 2. Create dashboard HTML page
  - [x] 2.1 Create `fortress/src/static/dashboard.html`
    - Single self-contained HTML file with all CSS and JS inline, no external dependencies
    - Dark theme: background `#1a1a2e`, card BG `#16213e`, accent `#0f3460`, success `#4ecca3`, warning `#f0a500`, error `#e74c3c`
    - RTL support via `dir="rtl"` on Hebrew text containers
    - Responsive CSS Grid layout with `auto-fit` / `minmax` for mobile (320px+)
    - Six sections: System Health, Today stats, Open Items, Open Bugs, Recent Activity, Family Members
    - Status indicators: 🟢 connected, 🟡 warning/no_key, 🔴 disconnected/error
    - Auto-refresh every 30 seconds via `setInterval` calling `GET /dashboard/data`
    - Connection lost indicator on fetch failure, auto-clears on reconnect
    - Display uptime in human-readable format (Xd Xh Xm)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Update main.py — static files, dashboard router, uptime
  - Add `import time` and set `APP_START_TIME = time.time()` at module level
  - Add `from fastapi.staticfiles import StaticFiles`
  - Add `from src.routers import dashboard`
  - Add `app.include_router(dashboard.router)` after existing router registrations
  - Add `app.mount("/static", StaticFiles(directory="src/static"), name="static")` after router includes
  - _Requirements: 4.1, 4.2, 6.1_

- [x] 4. Checkpoint — Verify dashboard serves and returns data
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create startup scripts
  - [x] 5.1 Create `fortress/scripts/open_dashboard.sh`
    - Executable bash script that opens `http://localhost:8000/dashboard` using `open` (macOS)
    - Add a short sleep (2s) before opening to allow the app to start
    - _Requirements: 5.1_

  - [x] 5.2 Update `fortress/scripts/setup_mac_mini.sh`
    - Add invocation of `open_dashboard.sh` after the health checks section (step 8)
    - _Requirements: 5.2_

- [x] 6. Create dashboard tests
  - [x] 6.1 Create `fortress/tests/test_dashboard.py` with unit tests
    - Follow existing patterns from `conftest.py`: use `mock_db`, `client` fixtures
    - Mock health checks at `src.routers.dashboard` import level (same as `test_health.py`)
    - Mock `httpx.AsyncClient` for WAHA health check
    - Patch `src.routers.dashboard.APP_START_TIME` for uptime tests
    - Tests to implement:
      - `test_dashboard_data_returns_200` — verify 200 status (Req 1.1, 7.2)
      - `test_dashboard_data_json_structure` — verify all top-level keys present (Req 1.2, 1.3, 1.5, 1.9, 7.2)
      - `test_dashboard_health_all_services` — mock all 5 services connected, verify health object (Req 1.2)
      - `test_dashboard_today_counts` — mock DB with specific dates, verify today-only filtering (Req 1.3, 7.3)
      - `test_dashboard_error_count_hebrew_fallback` — mock conversations with/without HEBREW_FALLBACK, verify count (Req 1.4, 7.4)
      - `test_dashboard_open_items` — mock tasks/bugs with mixed statuses, verify counts (Req 1.5)
      - `test_dashboard_recent_conversations_limit` — verify max 20 records, ordered desc (Req 1.6, 7.5)
      - `test_dashboard_open_bugs_filter` — verify only "open" bugs returned (Req 1.7, 7.6)
      - `test_dashboard_family_members_active` — verify only active members returned (Req 1.8)
      - `test_dashboard_system_info` — verify version, uptime_seconds >= 0, app_start_time ISO format (Req 1.9, 6.2, 6.3, 7.7)
      - `test_waha_health_connected` — mock httpx 200, verify "connected" (Req 2.2)
      - `test_waha_health_disconnected_non_200` — mock httpx 500, verify "disconnected" (Req 2.3)
      - `test_waha_health_disconnected_error` — mock httpx ConnectError, verify "disconnected" (Req 2.3)
      - `test_dashboard_page_endpoint` — GET /dashboard returns 200 (Req 4.2)
      - `test_uptime_non_negative` — mock APP_START_TIME in past, verify uptime >= 0 (Req 6.2)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 7. Checkpoint — Run full test suite
  - Ensure all tests pass (existing 303 + new dashboard tests), ask the user if questions arise.

- [x] 8. Update documentation
  - [x] 8.1 Update `fortress/docker-compose.yml` with dashboard URL comment
    - Add a comment near the fortress service ports section noting the dashboard URL
    - _Requirements: 8.1_

  - [x] 8.2 Update `README.md` — mention dashboard in STABLE-6
    - Add admin dashboard mention to the STABLE-6 row in the roadmap table
    - _Requirements: 8.1_

- [-] 9. Final checkpoint — Run all tests and push
  - Ensure all tests pass, ask the user if questions arise.
  - Push to origin main when everything is green.

## Notes

- All code is Python (FastAPI). No pseudocode in design — language is already determined.
- Tests follow existing `conftest.py` patterns: `mock_db` (MagicMock(spec=Session)), `client` (TestClient with DB override).
- No new database tables or migrations needed — dashboard reads from existing tables.
- The dashboard HTML is fully self-contained (no CDN, no frameworks).
- Checkpoints ensure incremental validation before moving forward.
