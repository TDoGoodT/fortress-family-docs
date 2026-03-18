# Fortress Current State Verified v1

## Status

- Status: ACTIVE
- Authority Type: VERIFIED CURRENT STATE
- Scope: מה ממומש ומאומת כרגע בריפו
- Last Verified: Sprint 4

## Purpose

המסמך הזה הוא מקור האמת למצב הממומש והמאומת של הריפו.

הוא לא מחליף מסמכי ארכיטקטורה canonical.
הוא כן גובר עליהם בכל שאלה של "מה באמת עובד עכשיו".

## Verified System State

מה מאומת:

- PostgreSQL הוא רכיב הריצה המרכזי.
- `infra/db/apply_migrations.sh` מצליח להקים בסיס נתונים נקי וריק בצורה דטרמיניסטית.
- `public.schema_migrations` משמש כ־migration ledger פעיל.
- קיימים schemas ושכבות עבודה: `public`, `ingestion`, `core`, `query`.
- קיימות טבלאות canonical פעילות עבור:
  - `core.document`
  - `core.person`
  - `core.task`
  - `core.account`
- קיימים processors ו־projection checks עבור document/person/task/account.
- rerun של migration runner על DB שכבר הוקם מדלג על migrations שכבר נרשמו.

## Verified Limitations

- `check_ledger_integrity.sh` עדיין מדווח על 5 `hash_chain_mismatch` שנמצאים בחקירה.
- הראיות הנוכחיות מצביעות על פער ordering/diagnostic, לא על corruption מוכח.
- `infra/runtime/intake_filesystem_inbox.sh` עוצר בפועל אחרי:
  - `ingestion.run`
  - `ingestion.run_state`
  - `ingestion.raw_object`
- אין כיום runtime step מחובר שמקדם filesystem intake ל־:
  - `ingestion.raw_record`
  - `ingestion.normalized_record`
  - `ingestion.canonical_handoff_request`
- לכן filesystem intake אינו end-to-end עד canonical aggregates.

## Document Interpretation Rule

- למסמכי `architecture/core`, `architecture/ingestion`, `architecture/security`, `architecture/ai`, `architecture/openclaw` יש ערך כיעד ארכיטקטוני.
- אין להניח שמסמך ACTIVE/CANONICAL משקף בהכרח implementation verified.
- לשאלות על מצב נוכחי:
  1. לקרוא את המסמך הזה
  2. לקרוא את `architecture/_meta/version-matrix.md`
  3. לאמת מול קוד, migrations, runtime scripts, ו־checks

## Recommended Reading Order

1. `architecture/_meta/fortress.current-state.verified.v1.md`
2. `architecture/_meta/version-matrix.md`
3. `architecture/core/fortress.core.event-ledger.v1.md`
4. `architecture/ingestion/fortress.ingestion.pipeline-architecture.v3.md`
5. `architecture/project/fortress.project.dependency-model.v2.md`
6. `README.md`

## Archived Operational Documents

המסמכים הבאים נשמרו בארכיון כי הם מתעדים snapshot היסטורי, evidence pack, או plan ישן, ועלולים להטעות אם קוראים אותם כמצב נוכחי:

- `architecture/_archive/project/fortress.project.execution-plan-to-production.v1.md`
- `architecture/_archive/project/fortress.project.stage-a-baseline-evidence.v1.md`
- `architecture/_archive/project/fortress.project.stage-a-daily-wrapup.md`
- `architecture/_archive/project/fortress.project.controlled-filesystem-inbox-intake-plan.v1.md`
- `architecture/_archive/infra/fortress.infra.clean-baseline.v1.md`
