הערת merge קצרה:

- `034a_core_account_alignment.sql` דורשת ולידציית follow-up של מבנה `core.account` על בסיסי נתונים קיימים, כדי לוודא שהטבלה הקיימת תואמת ל־shape המצופה (`account_id`, `household_id`, `account_label`, `account_kind`, `created_at`).
- `029_core_person_created_contract.sql` ו־`030_core_person_projection_rule.sql` אינן bookkeeping-only: הן גם מבצעות `CREATE OR REPLACE VIEW`, ולכן עשויה להיות להן השפעת runtime על בסיסי נתונים קיימים.
