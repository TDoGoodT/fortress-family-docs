# Fortress — Household Data Library

Fortress is a data platform for household management. It ingests documents from multiple channels (WhatsApp, email, bulk upload), extracts structured data using OCR and LLM pipelines, and serves that data to intelligent agents through a permissioned API.

Think of it as a **municipal library for your household** — documents come in through the intake desk, get cataloged and shelved in the right section, and agents (the librarians and specialists) access the shelves with room-specific keys.

## Architecture

```mermaid
flowchart TB
    subgraph INGESTION["📥 Ingestion Layer"]
        WA[WhatsApp]
        EM[Email]
        UP[Upload]
        DL[Media Download]
        DP["Document Pipeline\nOCR → Classify → Extract → Persist"]
    end

    subgraph LIBRARY["🗄️ Data Library — Postgres"]
        direction LR
        T1[(documents)]
        T2[(salary_slips)]
        T3[(contracts)]
        T4[(insurance_policies)]
        T5[(utility_bills)]
        T6[(facts)]
        T7[(tasks)]
        T8[(memories)]
    end

    subgraph API["🔌 Data Access API — REST"]
        A1["POST /api/v1/query"]
        A2["POST /api/v1/ingest"]
        A3["GET /api/v1/documents"]
        A4["GET /api/v1/facts"]
    end

    subgraph AGENTS["🤖 Agent Layer — Hermes"]
        direction LR
        AG1[Orchestrator]
        AG2[Librarian]
        AG3["Domain Specialists\nFinance · Insurance"]
    end

    WA & EM & UP --> DL --> DP --> LIBRARY
    LIBRARY --> API
    API --> AGENTS
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
