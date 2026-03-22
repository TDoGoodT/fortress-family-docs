# Fortress — Future Roadmap

Last updated: 2026-03-22
Author: Segev Ben-Zur + Architecture Advisor

This document captures future development plans beyond the current
STABLE and SMART phases. These ideas are preserved here so they are
not lost between development sessions.

---

## Phase: DEEP — Intelligence Layer

### DEEP-1: Financial Intelligence
- Monthly expense summary (auto-generated, sent via WhatsApp)
- "כמה שילמנו על חשמל השנה?" → instant answer from transactions
- Anomaly alerts: "החשמל החודש גבוה ב-30% מהממוצע"
- Forecasts: "בקצב הזה תסיימו את השנה ב-₪X"
- Category breakdown with trends
- Prerequisites: OCR working, 3+ months of transaction data

### DEEP-2: Smart Document Management
- Auto-classification (invoice/contract/receipt/letter)
- Smart search: "תמצא את החוזה עם בעל הבית"
- Document-triggered reminders: "החוזה נגמר בעוד 3 חודשים"
- Organized archive with auto-tagging
- Duplicate detection across uploads
- Prerequisites: OCR, RAG, NAS

### DEEP-3: Proactive Agent
- Agent initiates conversations, not just responds
- "שגב, מחר יש טסט לאוטו. רוצה שאתאם תור?"
- "חן, ראיתי שחשבון הארנונה הגיע. רוצה שאזכיר?"
- "לא שילמתם חשמל החודש — רוצים שאזכיר מחר?"
- Morning briefing: tasks + upcoming bills + calendar
- Prerequisites: Scheduler, Financial Intelligence, stable memory

### DEEP-4: Family Knowledge Base
- Grandma's recipe book → searchable via RAG
- Medical info (allergies, medications) → accessible
- Important contacts (doctor, plumber, electrician)
- "מי השרברב שהיה אצלנו בינואר?"
- Family document archive — searchable across years
- Prerequisites: RAG, bulk import complete

---

## Phase: DATA-LOAD — Historical Data Import

### Problem
Average family has 5-10 years of invoices, contracts, receipts.
Can't upload 500 documents one by one via WhatsApp.

### Three Import Tracks

**Track 1: Bulk Scan (the big one)**
Physical documents → Scanner/Phone → Folder → Bulk Import Script
Script: OCR → Classify → Extract → DB + NAS

**Track 2: Email Import**
Gmail/Outlook → Search "חשבונית"/"קבלה" → Download attachments → Bulk Import

**Track 3: Ongoing (already exists)**
Daily: Photo → WhatsApp → Fortress
Email: Forward → Fortress (Phase 7)

### Bulk Import Architecture
```
scripts/bulk_import.sh       ← CLI entry point
src/services/bulk_importer.py ← Core logic
```

Flow per file:
1. Detect file type (PDF, image, document)
2. OCR → extract text (Bedrock Vision)
3. AI classification → type, vendor, amount, date
4. Save to DB (documents + transactions)
5. Move to NAS (organized: /year/month/)
6. Create task if unpaid bill detected
7. Output: ImportReport with stats

### Import Strategy (gradual, not all at once)
- Week 1: Last year's invoices (50-100 docs) → verify OCR accuracy
- Week 2: 2-3 years back
- Week 3: Contracts and important documents
- Week 4: Everything else

### Dry Run Support
```bash
./scripts/bulk_import.sh ~/Documents/bills --dry-run
# Shows: file count, estimated cost, estimated time
# Does NOT import anything
```

### Prerequisites
- SMART-1 (OCR) must be working
- SMART-3 (NAS) must be configured
- Bedrock Vision access enabled

---

## Phase: CONNECT — External Integrations

### CONNECT-1: Bank Integration
- API connection to Israeli banks (if available)
- Auto-import transactions
- "כמה יצא מהעו"ש החודש?"
- Real-time balance alerts

### CONNECT-2: Calendar Sync
- Google Calendar integration
- Tasks with dates → calendar events
- "מה יש לנו השבוע?" → combined tasks + calendar
- Birthday reminders from family data

### CONNECT-3: Smart Home
- Home Assistant integration
- "כבה אורות" / "מה הטמפרטורה?"
- Automation: "שכחת לכבות מזגן"
- Energy monitoring tied to financial tracking

### CONNECT-4: Shopping Lists
- "תוסיף חלב לרשימה" → shared shopping list
- Share list with חן via WhatsApp
- "מה צריך לקנות לשבת?"
- Track spending by category

---

## Phase: SCALE — Multi-Household (Optional)

Only if Segev decides to make Fortress a product.

### SCALE-1: Multi-Tenant
- Each family = separate tenant
- DB isolation per household
- Self-service onboarding

### SCALE-2: Skill Marketplace
- Families share useful skills
- "חיבור לחברת חשמל" = downloadable skill
- Community-driven feature expansion

### SCALE-3: SaaS
- Fortress as a service
- Monthly subscription per family
- Managed hosting or self-hosted option

---

## Development Timeline Estimate

| When | What |
|------|------|
| Now | STABLE phases (stabilization) |
| Month 1 | SMART 1-4 (OCR, RAG, NAS, Email) |
| Month 2 | DATA-LOAD (bulk import historical docs) |
| Month 2-3 | DEEP 1-2 (financial intelligence, smart docs) |
| Month 3-4 | DEEP 3-4 (proactive agent, knowledge base) |
| Month 4+ | CONNECT (integrations) |
| Future | SCALE (if product decision made) |

---

## Notes
- This document is a living plan — update as priorities change
- Each phase should have its own requirements doc before implementation
- Always stabilize before adding features
- The family's daily feedback drives priority
