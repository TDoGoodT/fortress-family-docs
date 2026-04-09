"""Browse formatter — renders waterfall views as WhatsApp-friendly Hebrew text."""
from __future__ import annotations

from src.services.document_browse_queries import CategoryItem, PeriodItem, DetailItem

_BACK_HINT = "💡 שלח 'חזרה' לחזור אחורה"


def format_category_view(categories: list[CategoryItem]) -> str:
    """Render numbered category list with counts."""
    lines = ["📁 המסמכים שלך:\n"]
    for i, cat in enumerate(categories, 1):
        lines.append(f"{cat.emoji} {i}. {cat.label} ({cat.count})")
    lines.append(f"\n{_BACK_HINT}")
    return "\n".join(lines)


def format_period_view(periods: list[PeriodItem], category_label: str) -> str:
    """Render numbered period list."""
    lines = [f"📅 {category_label}:\n"]
    for i, p in enumerate(periods, 1):
        count_str = f" ({p.count})" if p.count > 1 else ""
        lines.append(f"{i}. {p.label}{count_str}")
    lines.append(f"\n{_BACK_HINT}")
    return "\n".join(lines)


def format_detail_view(
    details: list[DetailItem],
    category_label: str,
    period_label: str,
) -> str:
    """Render document details or numbered list if multiple."""
    if not details:
        return f"לא נמצאו מסמכים ב{category_label} עבור {period_label}"

    if len(details) == 1:
        return _format_single_detail(details[0])

    # Multiple docs — numbered list for selection
    lines = [f"📄 {category_label} — {period_label}:\n"]
    for i, d in enumerate(details, 1):
        summary = d.display_name
        if "סכום" in d.display_fields:
            summary += f" ({d.display_fields['סכום']})"
        lines.append(f"{i}. {summary}")
    lines.append(f"\n{_BACK_HINT}")
    return "\n".join(lines)


def _format_single_detail(detail: DetailItem) -> str:
    """Format a single document's details."""
    lines = [f"📄 {detail.display_name}\n"]
    for key, value in detail.display_fields.items():
        lines.append(f"  {key}: {value}")
    lines.append(f"\n{_BACK_HINT}")
    return "\n".join(lines)


def format_error_range(n: int) -> str:
    """Format an out-of-range selection error."""
    return f"מספר לא תקין. בחר מספר בין 1 ל-{n}"
