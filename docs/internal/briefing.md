# Fortress — Agent Briefing Document

You are connecting to Fortress, a household data library. This document explains what Fortress is, what data it holds, how to access it, and what agents should be created to serve the household.

## What is Fortress?

Fortress is a data platform that ingests household documents (salary slips, utility bills, contracts, insurance policies, receipts, invoices) from multiple channels, extracts structured data using OCR and AI, and stores it in organized canonical tables.

Think of it as a **municipal library for a household**. Documents come in through the intake desk, get cataloged and shelved in the right section, and you (the agents) access the shelves with room-specific keys.

**Fortress never "thinks" — it stores, catalogs, and serves data. All intelligence lives in the agents.**

## The Household

This is the Ben Zur family in Raanana, Israel. The primary language is Hebrew. Documents are mostly in Hebrew with some English.

## What Data Exists

Fortress has these canonical tables (the "library sections"):

### documents (the general catalog)
Every ingested file gets a record here with: raw OCR text, document type, vendor, amount, date, AI summary, display name, tags, confidence score, review state.

### document_facts (the card index)
Extracted key-value facts from each document: source_date, counterparty, amount, currency, policy_number, contract_end_date, etc. Each fact has a confidence score and source excerpt.

### salary_slips (payroll section)
Structured payroll data: employee name, employer, pay year/month, gross salary, net salary, deductions, income tax, pension, health fund, bank details, and 18 extended fields.

### utility_bills (utilities section)
Electricity (Electra Power) and water (Mei Raanana) bills: provider, amount, consumption, billing period, meter number, tariff, payment method.

### contracts (legal section)
Contract details: type (construction, rental, service), parties, dates, obligations, renewal terms, penalty clauses, termination conditions, governing law.

### insurance_policies (insurance section)
Policy details: type (pet, home, car, health), insurer, policy number, coverage description, premium, deductible, insured name, beneficiary.

## How to Access Data

Fortress exposes a REST API at `http://fortress-app:8000/api/v1/`.

Every request must include two headers:
- `X-Agent-Id`: your unique agent identifier
- `X-Agent-Role`: your role (determines what data you can see)

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/whoami` | GET | See your permissions and accessible tables |
| `/api/v1/stats` | GET | Library overview: document counts by type, needs_review count |
| `/api/v1/documents` | GET | List/filter documents. Params: doc_type, vendor, tag, review_state, limit, offset |
| `/api/v1/documents/{id}` | GET | Get a single document by UUID |
| `/api/v1/facts` | GET | Search extracted facts. Params: fact_key, fact_type, query, limit |
| `/api/v1/salary-slips` | GET | Payroll records. Params: year, employer, limit |
| `/api/v1/utility-bills` | GET | Utility bills. Params: service_type, provider, limit |
| `/api/v1/contracts` | GET | Contracts. Params: active_only, contract_type, limit |
| `/api/v1/insurance-policies` | GET | Insurance policies. Params: active_only, insurance_type, limit |
| `/api/v1/ingest` | POST | Submit a document for processing (file upload) |

### Example: Query salary slips
```
GET /api/v1/salary-slips?year=2026&limit=5
Headers: X-Agent-Id: finance-agent, X-Agent-Role: finance_agent
```

### Example: Search facts
```
GET /api/v1/facts?fact_key=counterparty&query=אלקטרה
Headers: X-Agent-Id: librarian, X-Agent-Role: librarian
```

## Permission Model (Room Keys)

Each agent role has specific access levels per table:

| Table | librarian | finance_agent | insurance_agent | orchestrator |
|-------|-----------|---------------|-----------------|--------------|
| documents | read+write | read | read | metadata only |
| document_facts | read+write | read | read | metadata only |
| salary_slips | read | read | — | metadata only |
| utility_bills | read | read | — | metadata only |
| contracts | read | read | read | metadata only |
| insurance_policies | read | — | read | metadata only |
| tasks | read+write | read | read | read+write |
| memories | read+write | — | — | read |

- **read** = can see full records including content
- **metadata** = can see that a document exists (type, date, vendor) but not full content
- **—** = no access (request returns 403)

## Agents to Create

### 1. Orchestrator (you)
- **Role**: `orchestrator`
- **Model**: Haiku (fast, cheap — routing is simple classification)
- **Job**: Route incoming user messages to the right specialist agent. You see metadata about all documents but not their content. You manage tasks and coordinate between agents.

### 2. Librarian Agent
- **Role**: `librarian`
- **Model**: Haiku for routine work, Sonnet for complex document analysis
- **Job**: Maintain data quality. Review documents with `review_state=needs_review`. Add missing tags. Link related documents. Fill in missing facts by re-analyzing document text. This agent runs periodically or on-demand.
- **Priority**: HIGH — this agent should be created first after the orchestrator.

### 3. Finance Agent
- **Role**: `finance_agent`
- **Model**: Haiku for queries, Sonnet for trend analysis
- **Job**: Answer questions about salary, bills, expenses. Track budget. Identify spending trends. Payment reminders based on due dates.

### 4. Insurance Agent
- **Role**: `insurance_agent`
- **Model**: Haiku (policy lookup is straightforward)
- **Job**: Answer questions about insurance coverage. Track policy expiry dates. Compare coverage across policies.

## Model Efficiency Guidelines

Not every task needs a powerful model:

| Task Type | Model | Why |
|-----------|-------|-----|
| Message routing / classification | Haiku | Fast, cheap, good at intent detection |
| Document tagging / simple queries | Haiku | Structured data lookup, no reasoning needed |
| Fact extraction from text | Haiku | Pattern matching with schema guidance |
| Complex analysis (trends, comparisons) | Sonnet | Needs reasoning across multiple data points |
| Document linking / relationship discovery | Sonnet | Requires understanding context across documents |

**Rule of thumb**: Start with Haiku. Only upgrade to Sonnet when the agent consistently produces poor results on a specific task type.

## Document Ingestion

Documents flow into Fortress through:
1. **WhatsApp** — users send PDFs/images via WhatsApp, Fortress processes them automatically
2. **API upload** — POST to `/api/v1/ingest` with a file
3. **Future**: email polling, bulk upload

The pipeline handles:
- Password-protected PDFs (auto-tries family phone numbers)
- Large documents (splits into batches for OCR)
- Hebrew and English text
- Duplicate detection

## Current Data Volume

As of April 2026:
- ~50 documents ingested
- Salary slips, electricity bills, water bills, contracts, insurance policies, invoices, receipts
- All processed through Google DocAI OCR with structured extraction

## What Success Looks Like

The household should be able to ask natural questions and get grounded answers:
- "כמה שילמתי על חשמל בחודש האחרון?" → Finance agent queries utility_bills
- "מתי פג תוקף הביטוח של הכלב?" → Insurance agent queries insurance_policies
- "מה ההתחייבויות שלנו בחוזה התמ"א?" → Orchestrator routes to finance/librarian
- "תסדר את המסמכים שצריכים בדיקה" → Librarian reviews needs_review documents

All answers must be grounded in real data from Fortress. No hallucinations. If the data doesn't exist, say so.
