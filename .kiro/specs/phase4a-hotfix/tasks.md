# Phase 4A Hotfix — Implementation Tasks

- [x] 1. Fix config.py — Add WAHA_API_KEY
  - [x] 1.1 Add WAHA_API_KEY variable to src/config.py
- [x] 2. Fix whatsapp_client.py — Remove hardcoded key
  - [x] 2.1 Remove hardcoded API key and use config-driven conditional header
- [x] 3. Fix docker-compose.yml — WAHA config passthrough
  - [x] 3.1 Add WAHA_API_KEY to fortress service and WAHA credentials to waha service
- [x] 4. Fix .env.example — Clean up variables
  - [x] 4.1 Rewrite .env.example with all variables and correct defaults
- [x] 5. Add structured logging
  - [x] 5.1 Add logging to intent_detector.py
  - [x] 5.2 Add logging to model_router.py
  - [x] 5.3 Add logging to llm_client.py
- [x] 6. Add new WhatsApp client tests
  - [x] 6.1 Add test for API key sent when configured
  - [x] 6.2 Add test for no API key header when empty
- [x] 7. Run all tests — verify 87 existing tests pass
