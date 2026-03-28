from __future__ import annotations
"""Fortress Agent Personality — the soul of the system.

Loads personality from ``config/SOUL.md`` when available, falling back to
the hardcoded default below.
"""

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_PERSONALITY: str = (
    "# מי אני\n"
    "אני פורטרס, העוזר המשפחתי. אני חלק מהמשפחה.\n"
    "\n"
    "# איך אני מדבר\n"
    "- תמיד בעברית\n"
    "- קצר וענייני — זה וואטסאפ, לא מייל\n"
    "- חם ומשפחתי, לא רשמי ולא רובוטי\n"
    "- משתמש באימוג'י במידה — לא מוגזם\n"
    "- פונה בשם פרטי כשאני יודע מי מדבר\n"
    "- אם אני לא יודע משהו — אני אומר בכנות\n"
    "\n"
    "# מה אני עושה\n"
    "- מנהל משימות משפחתיות\n"
    "- שומר מסמכים וחשבוניות\n"
    "- עוזר לזכור דברים חשובים\n"
    "- עונה על שאלות לגבי מידע שיש לי\n"
    "- שומר על פרטיות — ילדים לא רואים מידע פיננסי\n"
    "\n"
    "# מה אני לא עושה\n"
    "- לא ממציא מידע שאין לי\n"
    "- לא שומר סיסמאות, קודים, או מידע רגיש בזיכרון\n"
    "- לא מתערב בהחלטות — רק מספק מידע ועוזר\n"
    "- לא שולח הודעות ארוכות\n"
    "\n"
    "# הטון שלי\n"
    '- "היי שגב! 😊" ולא "שלום, משתמש יקר"\n'
    '- "יצרתי את המשימה ✅" ולא "המשימה נוצרה בהצלחה במערכת"\n'
    '- "אין משימות פתוחות 🎉" ולא "לא נמצאו משימות במצב פתוח"\n'
    '- "לא הצלחתי להבין, אפשר לנסח אחרת?" ולא "שגיאה בעיבוד הבקשה"'
)


def _load_soul() -> str:
    """Load personality from SOUL.md file, falling back to hardcoded default."""
    from src.config import SOUL_MD_PATH

    # Try relative to the fortress/ directory (where the app runs)
    candidates = [
        SOUL_MD_PATH,
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), SOUL_MD_PATH),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    logger.info("Loaded personality from %s", path)
                    return content
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("Error loading SOUL.md from %s", path)
    logger.info("SOUL.md not found, using default personality")
    return _DEFAULT_PERSONALITY


PERSONALITY: str = _load_soul()

GREETINGS: dict[str, str] = {
    "morning": "בוקר טוב {name}! ☀️ מה נעשה היום?",
    "afternoon": "צהריים טובים {name}! 😊 איך אפשר לעזור?",
    "evening": "ערב טוב {name}! 🌙 מה שלומך?",
    "night": "עדיין ער/ה {name}? 😄 מה צריך?",
}

TEMPLATES: dict[str, str] = {
    "task_created": "יצרתי משימה: {title} ✅{due_date_text}",
    "task_completed": "משימה הושלמה: {title} ✅ כל הכבוד! 🎉",
    "task_list_empty": "אין משימות פתוחות! 🎉 יום נקי.",
    "task_list_header": "📋 המשימות שלך:\n",
    "document_saved": "שמרתי את הקובץ ✅ {filename}",
    "permission_denied": "אין לך הרשאה לזה 🔒",
    "unknown_member": "לא מכיר את המספר הזה. בקש מההורים להוסיף אותך.",
    "inactive_member": "החשבון שלך לא פעיל. פנה להורים.",
    "error_fallback": "משהו השתבש 😅 אפשר לנסות שוב?",
    "cant_understand": "לא הבנתי, {name}. אפשר לנסח אחרת? 🤔",
    "task_deleted": "משימה נמחקה: {title} ✅",
    "task_delete_which": "איזו משימה למחוק? 🤔\n{task_list}",
    "task_not_found": "לא מצאתי את המשימה הזו 🤷",
    "task_duplicate": "המשימה הזו כבר קיימת ✅",
    "document_list_header": "📁 המסמכים שלך:\n",
    "document_list_empty": "אין מסמכים שמורים 📂",
    "reminder_new_task": "📋 תזכורת: {title}\n📅 עד {due_date}\nנוצר אוטומטית מתבנית חוזרת.",
    "scheduler_summary": "🔄 סיכום יומי: נוצרו {count} משימות מתבניות חוזרות.",
    "recurring_list_header": "🔄 התזכורות החוזרות שלך:\n",
    "recurring_list_empty": "אין תזכורות חוזרות פעילות 📭",
    "recurring_list_item": "{index}. {title} — {frequency} (הבא: {next_due_date})",
    "recurring_created": "יצרתי תזכורת חוזרת: {title} ✅\nתדירות: {frequency}\nהבא: {next_due_date}",
    "recurring_deleted": "תזכורת חוזרת בוטלה: {title} ✅",
    "recurring_not_found": "לא מצאתי את התזכורת הזו 🤷",
    "bug_reported": "באג נרשם ✅\n📝 {description}",
    "bug_list_header": "🐛 באגים פתוחים:\n",
    "bug_list_empty": "אין באגים פתוחים! 🎉",
    "bug_list_item": "{index}. {description}\n   📅 {created_at}",
    "confirm_delete": "למחוק את '{title}'? (כן/לא)",
    "action_cancelled": "בוטל ✅",
    "cancelled": "בסדר, עזבתי 😊",
    "task_updated": "משימה עודכנה: {title} ✅{changes}",
    "task_update_which": "איזו משימה לעדכן? 🤔\n{task_list}",
    "verification_failed": "משהו השתבש בשמירה 😅 אפשר לנסות שוב?",
    "multi_intent_summary": "ביצעתי כמה דברים:\n\n{responses}",
    "clarify": "לא הייתי בטוח מה התכוונת 🤔\nבחר אפשרות:\n{options}",
    "clarify_option": "{number}. {label}",
    "bulk_delete_confirm": "למחוק את כל {count} המשימות? 😮\n{task_list}\n\n(כן/לא)",
    "bulk_deleted": "{count} משימות נמחקו ✅",
    "bulk_range_confirm": "למחוק משימות {start}-{end}?\n{task_list}\n\n(כן/לא)",
    "task_assigned_notification": "📋 {sender_name} הקצה לך משימה: {title}",
    "need_list_first": "שלח 'משימות' קודם כדי לראות את הרשימה, ואז תוכל לבחור לפי מספר 📋",
    "task_similar_exists": "כבר יש משימה דומה: '{similar_title}'\nליצור בכל זאת את '{title}'? (כן/לא)",
    "info_stored": "שמרתי את המידע ✅\n{content}",
    # Morning briefing
    "morning_briefing": "בוקר טוב {name}! ☀️\n\n{items}\n\nמה תרצה לעשות?",
    "briefing_tasks": "📋 {count} משימות פתוחות",
    "briefing_recurring": "🔄 {next_title} בעוד {days} ימים",
    "briefing_docs": "📄 {count} מסמכים חדשים",
    "briefing_bugs": "🐛 {count} באגים פתוחים",
    "no_report_yet": "אין דוח מוכן עדיין. הדוח הבא ב-15 לחודש 📊",
    # Memory
    "pii_detected": "זיהיתי מידע אישי רגיש בהודעה שלך והגנתי עליו 🔒",
    "memory_excluded": "אני לא שומר מידע מסוג זה 🔒",
    "memory_list_empty": "אין זכרונות שמורים",
    "memory_list_header": "🧠 זכרונות:\n",
    # Deploy
    "deploy_started": "מתחיל עדכון מערכת... ⏳",
    "deploy_success": "המערכת עודכנה בהצלחה ✅\n{details}",
    "deploy_failed": "העדכון נכשל ❌\n{details}",
    "deploy_status": "סטטוס מערכת:\n{status}",
    "deploy_restarted": "המערכת הופעלה מחדש ✅",
    "deploy_not_configured": "Deploy secret לא מוגדר. הגדר DEPLOY_SECRET ב-.env",
    "deploy_rate_limited": "יותר מדי בקשות. נסה שוב בעוד 10 דקות ⏰",
}

_PRIORITY_EMOJI: dict[str, str] = {
    "urgent": "🔴",
    "high": "🟡",
    "normal": "🟢",
    "low": "⚪",
}


def get_greeting(name: str, hour: int) -> str:
    """Return a time-of-day greeting formatted with *name*.

    Hour ranges (using ``hour % 24``):
    - 5–11  → morning
    - 12–16 → afternoon
    - 17–21 → evening
    - else   → night
    """
    h = hour % 24
    if 5 <= h <= 11:
        key = "morning"
    elif 12 <= h <= 16:
        key = "afternoon"
    elif 17 <= h <= 21:
        key = "evening"
    else:
        key = "night"
    return GREETINGS[key].format(name=name)


def format_task_created(title: str, due_date: str | None = None) -> str:
    """Return a Hebrew confirmation for a newly created task."""
    due_date_text = f"\nעד: {due_date}" if due_date else ""
    return TEMPLATES["task_created"].format(title=title, due_date_text=due_date_text)


def format_task_list(tasks: list[dict]) -> str:
    """Return a formatted Hebrew task list, or the empty-list template."""
    if not tasks:
        return TEMPLATES["task_list_empty"]

    lines: list[str] = [TEMPLATES["task_list_header"]]
    for i, task in enumerate(tasks, 1):
        priority = getattr(task, "priority", None) or (task.get("priority") if isinstance(task, dict) else None) or "normal"
        emoji = _PRIORITY_EMOJI.get(priority, "🟢")
        title = getattr(task, "title", None) or (task.get("title", "") if isinstance(task, dict) else "")
        due = getattr(task, "due_date", None) or (task.get("due_date") if isinstance(task, dict) else None)
        due_text = f" (עד {due})" if due else ""
        lines.append(f"{i}. {emoji} {title}{due_text}")

    return "\n".join(lines)


_DOC_TYPE_EMOJI: dict[str, str] = {
    "document": "📄",
    "image": "🖼️",
    "spreadsheet": "📊",
    "other": "📎",
}


def format_document_list(documents: list) -> str:
    """Return a formatted Hebrew document list, or the empty-list template."""
    if not documents:
        return TEMPLATES["document_list_empty"]

    lines: list[str] = [TEMPLATES["document_list_header"]]
    for i, doc in enumerate(documents, 1):
        doc_type = getattr(doc, "doc_type", None) or (doc.get("doc_type") if isinstance(doc, dict) else None) or "other"
        emoji = _DOC_TYPE_EMOJI.get(doc_type, "📎")
        filename = getattr(doc, "original_filename", None) or (doc.get("original_filename") if isinstance(doc, dict) else None) or "ללא שם"
        created_at = getattr(doc, "created_at", None) or (doc.get("created_at") if isinstance(doc, dict) else None)
        date_text = str(created_at)[:10] if created_at else ""
        lines.append(f"{emoji} {i}. {filename}\n   📅 {date_text}")

    return "\n".join(lines)


# Hebrew frequency display map
_FREQUENCY_HEBREW: dict[str, str] = {
    "daily": "יומי",
    "weekly": "שבועי",
    "monthly": "חודשי",
    "yearly": "שנתי",
}


def format_recurring_list(patterns: list) -> str:
    """Return a formatted Hebrew recurring-pattern list, or the empty-list template."""
    if not patterns:
        return TEMPLATES["recurring_list_empty"]

    lines: list[str] = [TEMPLATES["recurring_list_header"]]
    for i, pattern in enumerate(patterns, 1):
        title = getattr(pattern, "title", None) or (pattern.get("title", "") if isinstance(pattern, dict) else "")
        frequency = getattr(pattern, "frequency", None) or (pattern.get("frequency", "") if isinstance(pattern, dict) else "")
        frequency_heb = _FREQUENCY_HEBREW.get(frequency, frequency)
        next_due_date = getattr(pattern, "next_due_date", None) or (pattern.get("next_due_date") if isinstance(pattern, dict) else None)
        lines.append(
            TEMPLATES["recurring_list_item"].format(
                index=i, title=title, frequency=frequency_heb, next_due_date=next_due_date,
            )
        )

    return "\n".join(lines)


def format_bug_list(bugs: list) -> str:
    """Return a formatted Hebrew bug list, or the empty-list template."""
    if not bugs:
        return TEMPLATES["bug_list_empty"]

    lines: list[str] = [TEMPLATES["bug_list_header"]]
    for i, bug in enumerate(bugs, 1):
        description = getattr(bug, "description", None) or (bug.get("description", "") if isinstance(bug, dict) else "")
        created_at = getattr(bug, "created_at", None) or (bug.get("created_at") if isinstance(bug, dict) else None)
        date_text = str(created_at)[:10] if created_at else ""
        lines.append(
            TEMPLATES["bug_list_item"].format(
                index=i, description=description, created_at=date_text,
            )
        )

    return "\n".join(lines)
