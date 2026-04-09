# Fortress — Household Data Library

Fortress is a data platform for household management. It ingests documents from multiple channels (WhatsApp, email, bulk upload), extracts structured data using OCR and LLM pipelines, and serves that data to intelligent agents through a permissioned API.

Think of it as a **municipal library for your household** — documents come in through the intake desk, get cataloged and shelved in the right section, and agents (the librarians and specialists) access the shelves with room-specific keys.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                          │
│  WhatsApp ─┐                                                    │
│  Email ────┤──→ Media Download ──→ Document Pipeline ──→ DB     │
│  Upload ───┘    (decrypt if needed)  (OCR → Classify →          │
│                                       Extract → Persist)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LIBRARY (Postgres)                    │
│                                                                 │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────────┐ │
│  │ documents│ │ salary_slips │ │ contracts │ │   insurance   │ │
│  │          │ │              │ │           │ │   _policies   │ │
│  └──────────┘ └──────────────┘ └───────────┘ └───────────────┘ │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────────┐ │
│  │  facts   │ │ utility_bills│ │   tasks   │ │   memories    │ │
│  └──────────┘ └──────────────┘ └───────────┘ └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DATA ACCESS API (REST)                      │
│                                                                 │
│  POST /api/v1/query     — structured data queries               │
│  POST /api/v1/ingest    — submit document for processing        │
│  GET  /api/v1/documents — list/search documents                 │
│  GET  /api/v1/facts     — search extracted facts                │
│                                                                 │
│  Every request includes agent_id + agent_role                   │
│  Fortress checks permissions before returning data              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AGENT LAYER (Hermes)                       │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Orchestrator│  │   Librarian  │  │  Domain Specialists   │  │
│  │   Agent     │  │    Agent     │  │  (Finance, Insurance) │  │
│  └─────────────┘  └──────────────┘  └───────────────────────┘  │
│                                                                 │
│  Agents live in Hermes, NOT in Fortress.                        │
│  Fortress is the library building. Agents are the staff.        │
└─────────────────────────────────────────────────────────────────┘
```

## Key Principle

**Fortress never "thinks" — it stores, catalogs, and serves data. All intelligence lives in the agents.**

## Document Pipeline (proven, production)

The ingestion pipeline handles:
- Google DocAI OCR (primary, best Hebrew support)
- Tesseract fallback (free, local)
- Bedrock Vision fallback (images)
- PDF batch splitting for large documents (>15 pages)
- Auto-decryption of password-protected PDFs
- Fingerprint-based resolver for known document families
- Keyword + LLM classification (filename-first priority)
- Chunked fact extraction for large documents
- Canonical table persistence (salary_slips, utility_bills, contracts, insurance_policies)
- Duplicate detection
- Auto-tagging and display name generation

## Permission Model

Agents access data through roles with table-level permissions:

```
Agent Role        │ salary_slips │ utility_bills │ contracts │ insurance │ documents │ tasks
──────────────────┼──────────────┼───────────────┼───────────┼───────────┼───────────┼──────
librarian         │ read         │ read          │ read      │ read      │ read+write│ read+write
finance_agent     │ read         │ read          │ read      │ —         │ read      │ read
insurance_agent   │ —            │ —             │ read      │ read      │ read      │ read
orchestrator      │ metadata     │ metadata      │ metadata  │ metadata  │ metadata  │ read+write
```

"metadata" = agent can see document exists (type, date, vendor) but not full content.

## Agents (Hermes)

Agents run in Hermes, external to Fortress. Key agents:

- **Orchestrator** — routes user requests to the right specialist agent
- **Librarian** — maintains data quality: reviews documents, adds tags, links related records, fills missing facts
- **Finance Agent** — budget tracking, expense trends, payment reminders
- **Insurance Agent** — policy management, coverage analysis, renewal tracking

## Quick Start

```bash
cd fortress
cp .env.example .env
docker compose up -d
bash scripts/apply_migrations.sh
curl -s http://localhost:8000/health
```

WAHA (WhatsApp) is behind a compose profile — start explicitly when needed:
```bash
docker compose --profile waha up -d
```

## Repo Layout

```
fortress/
├── src/
│   ├── api/                  # Data access API for agents (REST endpoints)
│   ├── services/
│   │   ├── documents.py      # Document ingestion pipeline
│   │   ├── document_processors/  # OCR backends (Google DocAI, Tesseract, Bedrock)
│   │   ├── document_classifier.py
│   │   ├── document_resolver.py
│   │   ├── document_fact_extractor.py
│   │   └── ...
│   ├── models/schema.py      # SQLAlchemy ORM models
│   ├── routers/              # FastAPI route handlers
│   └── config.py
├── migrations/               # SQL migrations (001-017)
├── tests/
├── docker-compose.yml
└── Dockerfile
```

## Database

Canonical tables:

| Table | Purpose | Key Fields |
|-------|---------|------------|
| documents | Raw document catalog | raw_text, doc_type, facts, summary, display_name |
| document_facts | Extracted fact index | fact_key, fact_value, confidence, source_excerpt |
| salary_slips | Payroll data | gross, net, deductions, tax, pension, 18 extended fields |
| utility_bills | Electricity, water, etc. | provider, amount, consumption, period, 13 extended fields |
| contracts | Legal agreements | parties, dates, obligations, penalties, governing law |
| insurance_policies | Insurance coverage | policy number, coverage, premium, deductible, beneficiary |

## Deployment (Mac Mini)

```bash
bash scripts/deploy.sh deploy_all   # pull + rebuild + migrations
bash scripts/deploy.sh status       # runtime status
```

## Tests

```bash
cd fortress
python -m pytest tests/ -q
```
