"""Fortress Agent Personality — the soul of the system."""

PERSONALITY: str = (
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
