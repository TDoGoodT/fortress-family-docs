from datetime import datetime, timedelta
import pytz

IL_TZ = pytz.timezone("Asia/Jerusalem")


def get_time_context() -> dict:
    """Get current time context for Israel timezone."""
    now = datetime.now(IL_TZ)
    tomorrow = now + timedelta(days=1)

    day_names_he = {
        0: "שני", 1: "שלישי", 2: "רביעי",
        3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"
    }

    return {
        "now": now.isoformat(),
        "today_date": now.strftime("%Y-%m-%d"),
        "today_day_he": f"יום {day_names_he[now.weekday()]}",
        "today_display": f"יום {day_names_he[now.weekday()]}, {now.day} ב{_month_name_he(now.month)} {now.year}",
        "tomorrow_date": tomorrow.strftime("%Y-%m-%d"),
        "tomorrow_display": f"יום {day_names_he[tomorrow.weekday()]}, {tomorrow.day} ב{_month_name_he(tomorrow.month)} {tomorrow.year}",
        "current_time": now.strftime("%H:%M"),
        "hour": now.hour,
    }


def _month_name_he(month: int) -> str:
    months = {
        1: "ינואר", 2: "פברואר", 3: "מרץ",
        4: "אפריל", 5: "מאי", 6: "יוני",
        7: "יולי", 8: "אוגוסט", 9: "ספטמבר",
        10: "אוקטובר", 11: "נובמבר", 12: "דצמבר"
    }
    return months.get(month, "")


def format_time_for_prompt() -> str:
    """Format time context string to inject into LLM prompts."""
    ctx = get_time_context()
    return (
        f"תאריך ושעה נוכחיים:\n"
        f"היום: {ctx['today_display']}, שעה {ctx['current_time']}\n"
        f"מחר: {ctx['tomorrow_display']}\n"
        f"תאריך היום: {ctx['today_date']}\n"
        f"תאריך מחר: {ctx['tomorrow_date']}"
    )
