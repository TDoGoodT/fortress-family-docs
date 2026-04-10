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
└─────────────────────────────────────────────────────────────────┘
```

## Key Principle

**Fortress never "thinks" — it stores, catalogs, and serves data. All intelligence lives in the agents.**

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

## Links

- [Architecture Overview](architecture/overview.md)
- [Setup Guide](setup.md)
- [Feature List](features.md)
- [Backlog](roadmap/backlog.md)
