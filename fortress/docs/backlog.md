# Fortress — Backlog & Known Issues

> כשתרצה לעשה סשן תיקונים, תגיד לקירו: "בוא נעבור על ה-backlog ונתקן משימה משימה"

---

## 🐛 באגים

### B1 — Recurring: תאריך הבא לא מחושב נכון
**תיאור:** כשיוצרים תזכורת חודשית עם יום ספציפי ("ב-10 בחודש"), התאריך הבא יוצא לא נכון (2026-04-27 במקום 2026-04-10).
**סיבה:** ה-LLM לא מחלץ `day_of_month` נכון מהטקסט העברי.
**קובץ:** `src/skills/recurring_skill.py`

### B2 — Recurring: תדירות מוצגת באנגלית
**תיאור:** הרשימה מציגה "monthly" במקום "חודשי".
**קובץ:** `src/skills/recurring_skill.py` / `src/prompts/personality.py`

### B3 — Morning briefing: "בעוד 0 ימים" כשאין recurring
**תיאור:** כשאין תזכורות חוזרות, ה-briefing מציג "— בעוד 0 ימים" במקום להסתיר את השורה.
**קובץ:** `src/skills/morning_skill.py` → `_briefing()`

### B4 — Deploy: הודעת סיום לא מגיעה
**תיאור:** אחרי `עדכן מערכת`, מגיעה "עדכון התחיל" אבל לא ברור אם הגיעה הודעת סיום.
**לבדוק:** האם `_notify()` ב-`deploy_listener.py` עובד end-to-end.

---

## ⚡ שיפורים

### I1 — git config: committer name/email
**תיאור:** כל commit יוצא עם "Segev Ben-Zur <fortress-ai@Segevs-Mac-mini.local>" אוטומטי עם אזהרה.
**פתרון:** `git config --global user.name "Segev"` + `git config --global user.email "..."`

### I2 — Recurring: תמיכה בעברית טבעית יותר
**תיאור:** לאפשר "כל שבוע ביום שישי", "כל שנה ב-15 בינואר" וכו'.
**קובץ:** `src/skills/recurring_skill.py` — שיפור ה-regex + LLM extraction

### I3 — Morning briefing: הצג שמות משימות, לא רק מספר
**תיאור:** "2 משימות פתוחות" — עדיף להציג את שמות המשימות עצמן.
**קובץ:** `src/skills/morning_skill.py` → `_briefing()`

### I4 — Deploy: הסר `--no-cache` מ-build
**תיאור:** `docker compose build --no-cache` לוקח 2-3 דקות. בלי זה — 30 שניות.
**סיכון:** לפעמים cache ישן גורם בעיות. לשקול.
**קובץ:** `fortress/scripts/deploy.sh`

### I5 — WAHA: session stability
**תיאור:** ה-session נפל כמה פעמים במהלך הסשן. לבדוק אם `WHATSAPP_RESTART_ALL_SESSIONS=true` עוזר או מזיק.
**קובץ:** `fortress/docker-compose.yml`

### I7 — Deploy: פקודות לא אינטואיטיביות
**תיאור:** המשתמש שלח "עדכון מערכת" במקום "עדכן מערכת" — לא עבד. צריך לתמוך בוריאנטים נפוצים.
**סטטוס:** תוקן חלקית (נוסף "עדכון מערכת" ל-regex)
**קובץ:** `src/skills/deploy_skill.py`
**תיאור:** `מחק 1` עובד אבל `מחק משימה 1` לא תמיד. לאחד את הלוגיקה.
**קובץ:** `src/skills/task_skill.py`

---

## 📋 פיצ'רים לשלב הבא (לא באגים)

- **תזכורות חד-פעמיות** — "תזכיר לי מחר", "תזכיר לי בשמונה בערב", "תזכיר לי בשבוע הבא", "תזכיר לי ב-15 באפריל". שונה מ-recurring (חוזר) — זו תזכורת חד-פעמית עם תאריך/שעה ספציפיים. דורש: טבלה חדשה ב-DB, scheduler שבודק כל דקה, ו-skill חדש.
- **RAG** — חיפוש סמנטי במסמכים (pgvector)
- **Folder Watcher** — מעקב אוטומטי אחרי תיקיית ה-SSD
- **Email Ingest** — IMAP polling לחשבוניות
- **Memory Skill** — הפעלת MemorySkill (כרגע מוקמנטת)
- **Financial summary** — סיכום הוצאות חודשי

---

## ✅ הושלם לאחרונה (28 מרץ 2026)

- **OpenRouter הוסר** — עברנו לבדרוק בלבד, הסרנו את OpenRouter מהקוד
- **Bedrock API Key** — מעבר ל-Bedrock API key authentication (במקום boto3)
- **Morning status** — נוסף פקודת "סטטוס" ל-morning skill
- **Docker compose cleanup** — הסרת version warning

---

*עודכן לאחרונה: 28 מרץ 2026*
