---
name: deploy
version: "1.0"
language: he
---

# DeploySkill — עדכון ופריסה מרחוק

## תיאור
מאפשר להורים לעדכן ולהפעיל מחדש את פורטרס ישירות מוואטסאפ.

## פקודות

| תבנית | פעולה | דוגמה |
|--------|-------|-------|
| `עדכן מערכת` / `deploy` / `עדכון` / `פרוס` | deploy | עדכן מערכת |
| `ריסטארט` / `restart` / `הפעל מחדש` | restart | ריסטארט |
| `סטטוס מערכת` / `status` | status | סטטוס מערכת |

## הרשאות
- הורים בלבד (role == "parent")

## אבטחה
- טוקן מ-.env (DEPLOY_SECRET), לא hardcoded
- Listener מאזין על 127.0.0.1 בלבד
- Rate limit: 3 בקשות ל-10 דקות
- כל בקשה נבדקת: method, content-type, JSON, token, action
