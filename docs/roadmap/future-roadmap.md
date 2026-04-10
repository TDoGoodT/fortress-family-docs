# Fortress — Future Roadmap

Last updated: March 2026

---

## Completed Phases

| Phase | Description | Tests | Date |
|-------|-------------|-------|------|
| 1.0 — Foundation | 6 tables, FastAPI, Docker, auth, audit | 10 | 2025 |
| 2.0 — Tasks | Tasks + recurring patterns | 28 | 2025 |
| 3.0 — WhatsApp | WAHA integration, message handler | 52 | 2025 |
| 3.5 — Deploy | Mac Mini deployment, permissions, seed | 52 | 2025 |
| 4A — Local AI | Ollama, intent detection, model router | 89 | 2025 |
| 4A — Hotfix | WAHA config, logging fixes | 89 | 2025 |
| 4B — Bedrock + Memory | AWS Bedrock, memory system | 91 | 2025 |
| 4B.5 — Model Routing | OpenRouter, 3-tier routing, fallbacks | 130 | 2025 |
| 4B.6 — Ollama Cleanup | Remove Ollama from critical path | 150 | 2025 |
| 4B.7 — Pipeline Resilience | JSON healing, response protection, logging | 175 | 2025 |
| STABLE-2 — Personality | Hebrew personality, templates, consistent tone | 201 | 2025 |
| STABLE-3 — Core Hardening | Delete tasks, ownership, dedup, prompt cleanup | 228 | 2025 |
| STABLE-4 — Document Flow | Document storage, metadata, personality templates | 254 | 2025 |
| STABLE-5 — Recurring Scheduler | Recurring scheduler, WhatsApp notifications | 254+ | 2025 |
| STABLE-6 — Early Production | Bug tracker, memory fix, session resilience, dashboard | 318 | 2025 |
| SPRINT-1 — State + Verification | Conversation state, time injection, confirmations | 365 | 2025 |
| SPRINT-2 — Intent + UX | Priority classification, multi-intent, bulk ops | 420+ | 2025 |
| R1 — Skills Engine Core | BaseSkill ABC, Registry, CommandParser, Executor, ResponseFormatter | 478 | 2026 |
| R2 — Core Skills Migration | Task, Recurring, Document, Bug, Chat, Memory, Morning skills | 627 | 2026 |
| R3 — Wire + Test + Deploy | E2E tests, permissions, confirmations, regression, merge to main | 689 | 2026 |
| R4 — Trim + Document + Organize | Delete old pipeline, clean deps, rewrite docs | 428 | March 2026 |

---

## Next Steps

**Immediate**: Deploy R4 to production -> Production week (monitor stability) -> SMART-1 (OCR)

| Phase | Priority | Description |
|-------|----------|-------------|
| SMART-1 — OCR | Next | Document intelligence: invoice scanning, receipt parsing via Bedrock Vision |
| SMART-2 — RAG | High | pgvector, document Q&A, contract analysis, searchable knowledge base |
| SMART-3 — NAS + Backup | High | NAS file storage, Backblaze B2 backup, organized archive |
| SMART-4 — Email | Medium | IMAP polling, auto-ingest invoices and receipts from email |
| Hardening | Medium | Monitoring, auto-restart, rate limiting, health alerts |

---

## New Skill Ideas

| Skill | Hebrew Name | Description |
|-------|-------------|-------------|
| ShoppingListSkill | רשימת קניות | Shared shopping lists, "תוסיף חלב לרשימה", share via WhatsApp |
| ExpenseSkill | מעקב הוצאות | Expense tracking, monthly summaries, category breakdown |
| RecipeSkill | מתכונים | Family recipe book, searchable, "מה מבשלים היום?" |
| ContactSkill | אנשי קשר | Important contacts (doctor, plumber), "מי השרברב שהיה אצלנו?" |
| CalendarSkill | יומן | Google Calendar sync, "מה יש לנו השבוע?", birthday reminders |

---

## Phase: DEEP — Intelligence Layer

### DEEP-1: Financial Intelligence
- Monthly expense summary (auto-generated, sent via WhatsApp)
- Anomaly alerts: spending spikes vs. average
- Forecasts and category breakdown with trends
- Prerequisites: OCR working, 3+ months of transaction data

### DEEP-2: Smart Document Management
- Auto-classification (invoice/contract/receipt/letter)
- Smart search: "find the landlord contract"
- Document-triggered reminders: "contract expires in 3 months"
- Duplicate detection across uploads
- Prerequisites: OCR, RAG, NAS

### DEEP-3: Proactive Agent
- Agent initiates conversations, not just responds
- Morning briefing: tasks + upcoming bills + calendar
- Payment reminders, appointment scheduling
- Prerequisites: Scheduler, Financial Intelligence, stable memory

### DEEP-4: Family Knowledge Base
- Searchable family knowledge via RAG
- Medical info (allergies, medications), important contacts
- Family document archive searchable across years
- Prerequisites: RAG, bulk import complete

---

## Phase: DATA-LOAD — Historical Data Import

### Problem
Average family has 5-10 years of invoices, contracts, receipts. Can't upload 500 documents one by one via WhatsApp.

### Three Import Tracks

1. **Bulk Scan**: Physical documents -> Scanner/Phone -> Folder -> Bulk Import Script (OCR -> Classify -> Extract -> DB + NAS)
2. **Email Import**: Gmail/Outlook -> Search invoices/receipts -> Download attachments -> Bulk Import
3. **Ongoing** (already exists): Daily photo -> WhatsApp -> Fortress

### Prerequisites
- SMART-1 (OCR) must be working
- SMART-3 (NAS) must be configured
- Bedrock Vision access enabled

---

## Phase: CONNECT — External Integrations

### CONNECT-1: Bank Integration
- API connection to Israeli banks (if available)
- Auto-import transactions, real-time balance alerts

### CONNECT-2: Calendar Sync
- Google Calendar integration
- Tasks with dates -> calendar events
- Birthday reminders from family data

### CONNECT-3: Smart Home
- Home Assistant integration
- Energy monitoring tied to financial tracking

### CONNECT-4: Shopping Lists
- Shared shopping list via WhatsApp
- Track spending by category

---

## Phase: SCALE — Multi-Household (Optional)

Only if Fortress becomes a product.

### SCALE-1: Multi-Tenant
- Each family = separate tenant, DB isolation, self-service onboarding

### SCALE-2: Skill Marketplace
- Families share useful skills, community-driven feature expansion

### SCALE-3: SaaS
- Fortress as a service, monthly subscription, managed or self-hosted

---

## Development Timeline Estimate

| When | What |
|------|------|
| Now | Deploy R4 to production |
| Week 1-2 | Production monitoring, stability |
| Month 1 | SMART-1 (OCR) + SMART-2 (RAG) |
| Month 2 | SMART-3 (NAS) + DATA-LOAD (bulk import) |
| Month 2-3 | DEEP-1 (financial intelligence) + DEEP-2 (smart docs) |
| Month 3-4 | DEEP-3 (proactive agent) + DEEP-4 (knowledge base) |
| Month 4+ | CONNECT (integrations) |
| Future | SCALE (if product decision made) |

---

## Notes
- This document is a living plan — update as priorities change
- Each phase should have its own requirements doc before implementation
- Always stabilize before adding features
- The family's daily feedback drives priority
