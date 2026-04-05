# Fortress Product Roadmap: Knowledge Ingestion, Retrieval & Automation

## Vision

Fortress evolves from a document storage bot into a **family knowledge system** — it ingests information from any source (documents, photos, pasted text, screenshots), extracts structured facts, stores them with temporal context, and enables both on-demand retrieval and automated periodic reports.

The agent loop (LLM + tool calling) is the brain. The knowledge layer is the memory. Automation is the muscle.

## Architecture Layers

### Layer 1: Knowledge Ingestion (what goes IN)

**Current state:** Documents via media upload (images/PDFs) → OCR → classification → fact extraction → storage.

**Target state:** Any input format → structured facts:
- Media upload (images, PDFs, Word docs) — already works
- Plain text messages — user pastes a recipe, bank balance, note, anything
- Screenshots — OCR extracts text, then same pipeline
- Forwarded messages — WhatsApp forwards treated as text input
- Future: email attachments, shared links

**Key principle:** The ingestion pipeline is format-agnostic. Whether the user sends a photo of a bank statement or types "יתרה בקופת גמל: 245,000 ₪", the system extracts the same structured facts.

### Layer 2: Knowledge Retrieval (what comes OUT)

**Current state:** Single-document queries ("what's the amount on this invoice?").

**Target state:** Cross-document, time-aware queries:
- Single document: "מה הסכום בחשבונית?" → amount from one document
- Cross-document: "כמה שילמנו על ביטוח השנה?" → aggregate across insurance documents
- Time-series: "מה השינוי בחסכון מחודש שעבר?" → compare facts across time periods
- Contextual: "מה היתרה הנוכחית בכל הקופות?" → latest balance per account

### Layer 3: Automation (things that happen WITHOUT user input)

**Current state:** Daily scheduler for recurring tasks/reminders.

**Target state:** Scheduled knowledge workflows:
- Monthly financial report — collect balances, compare to previous month, generate report
- Insurance renewal alerts — flag policies expiring within 30 days
- Document expiry tracking — contracts, warranties approaching end date
- Custom automations — user-defined periodic queries

## Sprint Plan

### Sprint 1: Text-Based Knowledge Ingestion ← CURRENT

**Goal:** Users can paste any text (recipe, bank balance, note) and the system classifies it, extracts facts, and stores it as a searchable document.

**Deliverables:**
- `save_text` tool — accepts raw text, runs through classification + fact extraction pipeline
- Agent recognizes when user is sharing information to save (vs asking a question)
- Stored as a Document with `source="text_message"`, full fact extraction
- Retrievable via existing search/query tools

**Success criteria:**
- User pastes a recipe → stored as document with recipe facts → retrievable via "יש לי מתכונים?"
- User types "יתרה בקופת גמל: 245,000 ₪" → stored with amount fact → retrievable via "כמה יש בקופת גמל?"

### Sprint 2: Financial Fact Types + Structured Ingestion

**Goal:** The system understands financial data — account balances, deposits, withdrawals — and stores them with temporal context.

**Deliverables:**
- New fact types: `balance`, `deposit`, `withdrawal`, `account_name`, `institution`, `liquid_amount`, `locked_amount`
- Financial document classifier improvements — recognize bank statements, savings reports, investment summaries
- Temporal tagging — every financial fact gets a `reporting_month` and `reporting_year`
- `save_financial_snapshot` tool — structured input for account balances

**Success criteria:**
- User sends photo of savings account statement → extracts balance, institution, date
- User types "מנורה: 180,000, הראל: 95,000, כלל: 120,000" → stores three balance facts with current month

### Sprint 3: Monthly Financial Report Automation

**Goal:** Automated monthly report that aggregates all financial data and shows changes.

**Deliverables:**
- `generate_financial_report` tool — aggregates balances by account, computes month-over-month delta
- Scheduled job (1st of each month) — auto-generates and sends report via WhatsApp
- Report format: table with account name, current balance, previous balance, change (₪ and %), liquid vs locked
- Total row with aggregate numbers
- `financial_report` command — on-demand report generation

**Success criteria:**
- On the 1st of each month, your wife receives a WhatsApp message with the full financial summary
- She can also ask "דוח חודשי" anytime to get the latest snapshot
- Report shows which accounts grew, which shrank, total family net worth trend

### Sprint 4: Cross-Document Queries + Intelligence

**Goal:** The agent can answer questions that span multiple documents and time periods.

**Deliverables:**
- Aggregation queries — "כמה שילמנו על ביטוח השנה?" sums amounts across insurance documents
- Trend queries — "איך השתנה החסכון ב-6 חודשים האחרונים?" shows time series
- Alert queries — "אילו פוליסות מתחדשות בחודש הקרוב?" checks expiry dates
- Smart suggestions — "שמתי לב שהביטוח עלה ב-15% מהשנה שעברה"

**Success criteria:**
- Natural Hebrew questions about family finances get accurate, data-backed answers
- The system proactively flags important changes or upcoming events

## Technical Foundation

All sprints build on the same core:
- **Agent loop** (built) — LLM decides intent, calls tools
- **Document model** (built) — documents + document_facts in PostgreSQL
- **Fact extraction pipeline** (built) — LLM-based structured extraction
- **Tool registry** (built) — easy to add new tools
- **Scheduler** (built) — APScheduler for periodic jobs
- **WhatsApp delivery** (built) — WAHA for sending reports

Each sprint adds new tools to the registry and new fact types to the extraction pipeline. The agent loop doesn't change — it just gets more tools to work with.
