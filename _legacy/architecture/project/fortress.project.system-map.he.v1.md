# Fortress 2 — מפת מערכת (System Map) בעברית

## תקציר מנהלים
Fortress היא תשתית ידע ביתית, local-first, שבה **Event Ledger** הוא עמוד השדרה הקנוני, שכבת **ingestion** מייצרת אירועים דטרמיניסטיים, שכבת **core** ממירה handoffים לישויות קנוניות, ושכבת **query** מגישה תצוגות קריאה לבית האב. AI ממוקם כשכבה נגזרת בלבד ואינו מקור אמת.

---

## 1) תתי־המערכות המרכזיות

### א. Event Ledger (ליבה עובדתית)
**מטרה:** לשמור היסטוריית אירועים append-only, עם מעטפת עקיבות ושרשרת hash.

**רכיבים מרכזיים:**
- `public.event_ledger` — טבלת האירועים הראשית.
- טריגרים שחוסמים `UPDATE/DELETE` (append-only).
- מעטפת אירוע: `actor_*`, `zone_context`, `correlation_id`, `causation_id`, `event_timestamp`.
- hash chaining דרך `previous_event_hash` ו-`current_event_hash`.

**איפה זה מוגדר:**
- `infra/db/001_event_ledger.sql`
- `infra/db/004_event_ledger_envelope.sql`
- `infra/db/005_event_ledger_hash_chaining.sql`

---

### ב. Ingestion (אזור קליטה דטרמיניסטי)
**מטרה:** לקלוט קבצים/רשומות גולמיות, לנרמל, ולהפיק handoff קנוני לליבה.

**רכיבים מרכזיים:**
- סכמות `ingestion.*`: `source`, `run`, `run_state`, `raw_object`, `raw_record`, `normalized_record`, `canonical_handoff_request`, `error`.
- חוזי כתיבה (Views) ל-ledger: `ingestion.ledger_contract_*`.
- תור פליטה אחוד ודטרמיניסטי: `ingestion.ledger_contract_emit_queue`.
- סקריפטים runtime לקליטת inbox ולפליטת אירועים.

**איפה זה מוגדר:**
- `infra/db/007_create_ingestion_tables.sql`
- `infra/db/023_contract_envelope_alignment.sql`
- `infra/runtime/intake_filesystem_inbox.sh`
- `infra/runtime/emit_ingestion_events.sh`

---

### ג. Canonical Handoff Processing (מעבר Zone C → Zone A)
**מטרה:** לקבוע סדר עיבוד דטרמיניסטי לבקשות handoff ולמנוע לוגיקת סדר אד-הוק בריצה.

**רכיבים מרכזיים:**
- `core.canonical_handoff_processing_queue` — תור עיבוד נגזר.
- `core.canonical_handoff_receipt` — קבלה קנונית שמוכיחה שה-handoff יושם.

**איפה זה מוגדר:**
- `infra/db/024_canonical_handoff_processor_contract.sql`
- `infra/db/008_create_core_handoff_receipt.sql`

---

### ד. Core Canonical Aggregates (יישויות קנוניות)
**מטרה:** להחזיק מצב קנוני (מסמכים/אנשים/משימות/חשבונות) שנוצר רק דרך אירועים וחוזים.

**רכיבים מרכזיים:**
- טבלאות: `core.document`, `core.person`, `core.task`, `core.account`.
- חוזים פר-aggregate: `core.ledger_contract_*_created`.
- חוקי הקרנה מה-ledger: `core.ledger_projection_*`.
- מעבדי handoff ייעודיים (runtime scripts) שמיישמים transaction קנוני: 
  1) בדיקת receipt, 
  2) כתיבת אירוע ל-ledger, 
  3) materialization לטבלת `core.*`, 
  4) כתיבת receipt.

**איפה זה מוגדר:**
- מסמכים: `infra/db/025..027`, `infra/runtime/process_document_handoffs.sh`
- אנשים: `infra/db/028..030`, `infra/runtime/process_person_handoffs.sh`
- משימות: `infra/db/031..033`, `infra/runtime/process_task_handoffs.sh`
- חשבונות: `infra/db/034..037`, `infra/runtime/process_account_handoffs.sh`

---

### ה. Query / Household Knowledge Layer (שכבת הגשה לקריאה)
**מטרה:** לספק שכבת שאילתות יציבה ונקייה לצריכה אפליקטיבית, ללא כתיבה וללא לוגיקה אימפרטיבית.

**רכיבים מרכזיים:**
- `query.household_accounts`
- `query.household_tasks`
- `query.household_documents`
- `query.household_state` (סיכום ביתי מאוחד)

**איפה זה מוגדר:**
- `infra/db/038_query_household_knowledge_layer.sql`

---

### ו. Infrastructure Governance
**מטרה:** להבטיח סדר מיגרציות דטרמיניסטי ובקרת גרסאות סכימה.

**רכיבים מרכזיים:**
- `public.schema_migrations` כמרשם מיגרציות append-only.
- runner דטרמיניסטי: `infra/db/apply_migrations.sh`.

---

## 2) איך תתי־המערכות מתקשרות

### זרימת נתונים מקצה לקצה
1. **קליטה חיצונית**: קבצים נקלטים מ-inbox חיצוני לסקריפט intake.
2. **Zone C**: נוצרים `ingestion.run` + ישויות קליטה (`raw_*`, `normalized_*`, `canonical_handoff_request`).
3. **חוזי ingestion**: Views מייצרים אירועים מוצעים עם `emit_dedup_key`.
4. **Emitter**: קורא רק את `ingestion.ledger_contract_emit_queue`, מסדר לפי `emit_seq`, וכותב ל-`public.event_ledger` באופן אידמפוטנטי.
5. **Queue קנוני**: `core.canonical_handoff_processing_queue` בונה סדר עיבוד ל-handoffים.
6. **Processor פר-aggregate** (document/person/task/account):
   - קורא חוזה `core.ledger_contract_*_created`
   - כותב אירוע `core.*.created` ל-ledger
   - מקרין לטבלת `core.*` דרך `core.ledger_projection_*`
   - כותב `core.canonical_handoff_receipt`
7. **Serving**: שכבת `query.*` מגישה תמונת מצב ביתית לקריאה.

---

## 3) איפה נמצאת הלוגיקה המרכזית (Core Logic)

### לוגיקה דקלרטיבית (SQL Views/Contracts) — זו הליבה הארכיטקטונית
- **חוקי "מה אמור להיכתב" ל-ledger**: ב-`ingestion.ledger_contract_*` וב-`core.ledger_contract_*`.
- **חוקי Projection**: ב-`core.ledger_projection_*`.
- **חוקי סדר/דטרמיניזם**: `ingestion.ledger_contract_emit_queue` + `core.canonical_handoff_processing_queue`.

### לוגיקה אימפרטיבית (runtime scripts) — מעטפת ביצוע נשלטת
- `infra/runtime/emit_ingestion_events.sh`: פליטת אירועי ingestion בפועל ל-ledger עם דה-דופ.
- `infra/runtime/process_*_handoffs.sh`: טרנזקציות קנוניות לכל aggregate.
- `infra/runtime/intake_filesystem_inbox.sh`: נקודת כניסה תפעולית לקליטת קבצים.

### גבולות אחריות ברורים
- **האמת ההיסטורית**: `public.event_ledger` בלבד.
- **מצב קנוני נוכחי**: טבלאות `core.*` (תוצר נגזר ומבוקר מאירועים).
- **שכבת הגשה**: `query.*` לקריאה בלבד.

---

## 4) מפה קצרה (ASCII)

```text
[Filesystem Inbox]
      |
      v
[intake_filesystem_inbox.sh]
      |
      v
[ingestion.* tables (Zone C)]
      |
      v
[ingestion.ledger_contract_* + emit_queue]
      |
      v
[emit_ingestion_events.sh]
      |
      v
[public.event_ledger (append-only + hash chain)]
      |
      +--> [core.canonical_handoff_processing_queue]
                |
                +--> [process_document_handoffs.sh] --> [core.document] -->
                +--> [process_person_handoffs.sh]   --> [core.person]   -->
                +--> [process_task_handoffs.sh]     --> [core.task]     --> [query.household_*]
                +--> [process_account_handoffs.sh]  --> [core.account]  -->
                              |
                              v
                     [core.canonical_handoff_receipt]
```

---

## 5) מסקנה ארכיטקטונית
Fortress בנויה סביב עיקרון: **אירוע קודם לישות**. רוב ה"שכל" של המערכת נמצא בחוזי SQL (contract/projection/queue), בעוד שסקריפטי ה-runtime הם מנגנוני הפעלה מבוקרים שמיישמים את החוזים טרנזקציונית. כך נשמרים דטרמיניזם, עקיבות, ואפשרות audit מלאה לאורך זמן.
