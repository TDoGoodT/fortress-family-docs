# Fortress Document Pipeline — Backlog & Roadmap

## Status: Active Development (April 2026)

---

## ✅ COMPLETED (April 9, 2026)

### Sprint: Google DocAI Integration & Document Processing
- [x] **Google DocAI Processor** — primary OCR for all PDFs and images, replacing Tesseract for Hebrew
- [x] **Processor Router** — auto-selects Google DocAI → Bedrock Vision → Tesseract based on doc type and filename
- [x] **Salary Slip Pipeline** — 12/12 fields verified correct (gross, net, deductions, pension, tax, employer, etc.)
- [x] **Extended Salary Slip Fields** — 18 new columns (employee_id, bank details, tax bracket, health fund, pension fund, etc.)
- [x] **Electricity Bill Pipeline** — Electra Power resolver, utility_bills table, extended fields (consumption_kwh, tariff, meter, savings)
- [x] **Water Bill Pipeline** — Mei Raanana resolver, routes to utility_bills with service_type=water, water-specific fields in raw_payload
- [x] **Duplicate Detection Notification** — user gets "המסמך הזה כבר קיים במערכת" instead of silent re-save
- [x] **Reprocess All Documents** — 48/48 docs reprocessed through Google DocAI, 0 failures
- [x] **Migrations 013-016** — salary_slips, utility_bills, extended fields for both

---

## 🔄 IN PROGRESS

### Waterfall Document Browsing UX
- [ ] When user asks "what documents do I have?" → show table categories (תלושי שכר: 15, חשבונות חשמל: 2, etc.)
- [ ] User picks a category → show months/periods available
- [ ] User picks a month → show specific document details
- [ ] Same pattern for invoices: month → vendor type → specific invoice

---

## 📋 NEXT UP

### Agent Data Access Layer (next chat session)
- [ ] Define agent permissions — which agents can access which tables
- [ ] Agents query structured tables (salary_slips, utility_bills), NOT raw documents
- [ ] Prevent hallucinations by grounding agent responses in real data
- [ ] Design tool schemas for agent data access (get_salary_summary, get_utility_bills, etc.)

### Bulk Upload
- [ ] Build bulk upload endpoint/script for batch document ingestion
- [ ] Collect real documents (salary slips, bills, contracts, receipts)
- [ ] Run through the pipeline to fill the database
- [ ] Validate data quality across all document types

### Email Integration & Automation
- [ ] Connect to email inbox for automatic document ingestion
- [ ] Auto-detect document attachments (PDF, images)
- [ ] Route through the same pipeline (Google DocAI → resolver → canonical tables)
- [ ] Notification to user when new documents are processed

### Smart Coalitions (End Goal)
- [ ] Intelligent agents that use structured data to help manage household
- [ ] Budget tracking across salary slips and utility bills
- [ ] Expense trend analysis (electricity usage over time, water consumption patterns)
- [ ] Payment reminders based on due dates
- [ ] Consider Hermes or OpenClaw for multi-agent orchestration
- [ ] Agent-to-agent communication for cross-domain insights

---

## Architecture Notes

### Document Flow
```
WhatsApp/Email/Upload → Media Download → Google DocAI OCR → Resolver (fingerprint matching)
→ Classifier (keyword + LLM) → Fact Extraction → Canonical Table Insert → User Notification
```

### Canonical Tables
| Table | Service Types | Key Fields |
|-------|--------------|------------|
| salary_slips | — | gross, net, deductions, tax, pension, employer, 18 extended fields |
| utility_bills | electricity, water, (future: gas, internet, arnona) | provider, amount, consumption, period, meter, 13 extended fields |
| documents | all | raw_text, doc_type, facts, summary, display_name |
| document_facts | all | fact_key, fact_value, confidence, source_excerpt |

### Processor Priority
1. Google DocAI (all PDFs and images) — best Hebrew OCR
2. Tesseract (fallback for DOCX, or when Google unavailable)
3. Bedrock Vision (fallback for images when Google unavailable)

### Resolvers (Fingerprint-Based Classification)
- `electra_utility_bill` — Electra Power electricity bills
- `mei_raanana_water_bill` — Mei Raanana water bills
- (future: gas, internet, arnona resolvers)
