"""Fortress Agent — tool registry.

Defines one Bedrock Converse toolSpec per user-facing skill action.
Tool names follow the pattern {skill}_{action}.
"""
from __future__ import annotations

from typing import Any

ToolSchema = dict[str, Any]

# ---------------------------------------------------------------------------
# Tool map: tool_name → (skill_name, action_name)
# ---------------------------------------------------------------------------

_TOOL_MAP: dict[str, tuple[str, str]] = {
    # Task management
    "task_create":      ("task", "create"),
    "task_list":        ("task", "list"),
    "task_complete":    ("task", "complete"),
    "task_delete":      ("task", "delete"),
    "task_delete_all":  ("task", "delete_all"),
    "task_update":      ("task", "update"),
    # Document management
    "document_list":         ("document", "list"),
    "document_search":       ("document", "search"),
    "document_fetch":        ("document", "fetch"),
    "document_query":        ("document", "query"),
    "document_recent":       ("document", "recent"),
    "document_recent_feed":  ("document", "recent_feed"),
    "document_tag_add":      ("document", "tag_add"),
    "document_tag_remove":   ("document", "tag_remove"),
    "document_tag_search":   ("document", "tag_search"),
    "document_recipe_list":   ("document", "recipe_list"),
    "document_recipe_search": ("document", "recipe_search"),
    "document_recipe_howto":  ("document", "recipe_howto"),
    # Memory
    "memory_list": ("memory", "list"),
    # Bug reporting
    "bug_report": ("bug", "report"),
    "bug_list":   ("bug", "list"),
    # Recurring patterns
    "recurring_create": ("recurring", "create"),
    "recurring_list":   ("recurring", "list"),
    "recurring_delete": ("recurring", "delete"),
    # System
    "system_help":   ("system", "help"),
    "system_cancel": ("system", "cancel"),
    "bedrock_cost":  ("system", "bedrock_cost"),
    # Knowledge ingestion
    "save_text": ("document", "save_text"),
    # Dev (admin-only)
    "dev_index": ("dev", "index"),
    "dev_query": ("dev", "query"),
    "dev_plan":  ("dev", "plan"),
}


def get_tool_map() -> dict[str, tuple[str, str]]:
    """Return mapping: tool_name → (skill_name, action_name)."""
    return dict(_TOOL_MAP)


# ---------------------------------------------------------------------------
# Tool schemas in Bedrock Converse toolSpec format
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS: list[ToolSchema] = [
    # ── Tasks ──────────────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "task_create",
            "description": "יצירת משימה חדשה. השתמש כשהמשתמש מבקש ליצור, להוסיף, או לרשום משימה.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "שם המשימה"},
                        "assignee_name": {"type": "string", "description": "שם בן המשפחה שהמשימה מיועדת לו"},
                        "due_date": {"type": "string", "description": "תאריך יעד בפורמט YYYY-MM-DD (אופציונלי)"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high", "urgent"],
                            "description": "עדיפות המשימה (אופציונלי)",
                        },
                        "category": {"type": "string", "description": "קטגוריה (אופציונלי)"},
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "task_list",
            "description": "הצגת רשימת המשימות הפתוחות. השתמש כשהמשתמש מבקש לראות משימות.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "task_complete",
            "description": "סימון משימה כהושלמה. השתמש כשהמשתמש אומר שסיים משימה.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string", "description": "מספר המשימה ברשימה"},
                        "title_query": {"type": "string", "description": "חלק משם המשימה לחיפוש"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "task_delete",
            "description": "מחיקת משימה ספציפית. השתמש כשהמשתמש מבקש למחוק משימה אחת.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string", "description": "מספר המשימה ברשימה"},
                        "title_query": {"type": "string", "description": "חלק משם המשימה לחיפוש"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "task_delete_all",
            "description": "מחיקת כל המשימות. השתמש רק כשהמשתמש מבקש למחוק את כל המשימות.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "task_update",
            "description": "עדכון פרטי משימה קיימת (שם, תאריך, עדיפות).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string", "description": "מספר המשימה ברשימה"},
                        "changes": {"type": "string", "description": "השינויים הרצויים"},
                    },
                    "required": ["index"],
                }
            },
        }
    },
    # ── Documents ──────────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "document_list",
            "description": "הצגת רשימת המסמכים השמורים. השתמש כשהמשתמש מבקש לראות מסמכים.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "document_search",
            "description": "חיפוש מסמכים לפי סוג או מילת מפתח. השתמש כשהמשתמש מחפש מסמך ספציפי.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "doc_type": {
                            "type": "string",
                            "description": "סוג המסמך: חוזים, חשבוניות, קבלות, ביטוח, אחריות",
                        },
                        "keyword": {"type": "string", "description": "מילת מפתח לחיפוש"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_fetch",
            "description": "מציאת מסמך לפי שם. השתמש כשהמשתמש מבקש מסמך ספציפי לפי שמו.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "doc_name": {"type": "string", "description": "שם המסמך לחיפוש"},
                    },
                    "required": ["doc_name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_query",
            "description": "שאלה על תוכן מסמך. חובה להשתמש בכלי הזה כשהמשתמש שואל שאלה על מסמך — סכום, תאריך, ספק, מועד תשלום, מה כתוב, מה רואים, פרטים כלשהם. אסור לענות על שאלות על מסמכים בלי הכלי הזה.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "השאלה על המסמך"},
                    },
                    "required": ["question"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_recent",
            "description": "הצגת המסמך האחרון שנשמר.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "document_recent_feed",
            "description": "הצגת 5 המסמכים האחרונים שנשמרו.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "מספר מסמכים להצגה (ברירת מחדל: 5)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_tag_add",
            "description": "הוספת תגית למסמך האחרון.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "שם התגית (ללא #)"},
                    },
                    "required": ["tag"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_tag_remove",
            "description": "הסרת תגית מהמסמך האחרון.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "שם התגית להסרה"},
                    },
                    "required": ["tag"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_tag_search",
            "description": "חיפוש מסמכים לפי תגית.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string", "description": "שם התגית לחיפוש"},
                    },
                    "required": ["tag"],
                }
            },
        }
    },
    # ── Recipes ────────────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "document_recipe_list",
            "description": "הצגת כל המתכונים השמורים. השתמש כשהמשתמש שואל על מתכונים.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "document_recipe_search",
            "description": "חיפוש מתכון לפי שם או מרכיב.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "recipe_query": {"type": "string", "description": "שם המתכון או מרכיב לחיפוש"},
                    },
                    "required": ["recipe_query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "document_recipe_howto",
            "description": "הצגת הוראות הכנה למתכון ספציפי.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "recipe_name": {"type": "string", "description": "שם המתכון"},
                    },
                    "required": ["recipe_name"],
                }
            },
        }
    },
    # ── Memory ─────────────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "memory_list",
            "description": "הצגת הזיכרונות השמורים של המשתמש.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    # ── Bug reporting ──────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "bug_report",
            "description": "דיווח על תקלה במערכת.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "תיאור התקלה"},
                    },
                    "required": ["description"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "bug_list",
            "description": "הצגת רשימת התקלות הפתוחות.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    # ── Recurring patterns ─────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "recurring_create",
            "description": "יצירת תזכורת חוזרת (שבועית, חודשית וכו').",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "שם התזכורת"},
                        "frequency": {
                            "type": "string",
                            "description": "תדירות: daily, weekly, monthly, yearly",
                        },
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "recurring_list",
            "description": "הצגת רשימת התזכורות החוזרות.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "recurring_delete",
            "description": "מחיקת תזכורת חוזרת.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "string", "description": "מספר התזכורת ברשימה"},
                    },
                    "required": ["index"],
                }
            },
        }
    },
    # ── System ─────────────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "system_help",
            "description": "הצגת רשימת הפקודות הזמינות. השתמש כשהמשתמש מבקש עזרה.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "system_cancel",
            "description": "ביטול פעולה ממתינה. השתמש כשהמשתמש אומר לא, בטל, עזוב.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "bedrock_cost",
            "description": "שאילתת עלויות Bedrock — מחזיר את העלות החודשית הנוכחית של שירותי Bedrock",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    # ── Knowledge ingestion ────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "save_text",
            "description": (
                "שמירת טקסט כמסמך ידע. השתמש כשהמשתמש משתף מידע לשמירה — "
                "מתכונים, נתונים פיננסיים, הערות, או כל מידע מובנה. "
                "אל תשתמש כשהמשתמש שואל שאלה או מנהל שיחה."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "הטקסט לשמירה"},
                        "title": {"type": "string", "description": "כותרת למסמך (אופציונלי)"},
                    },
                    "required": ["text"],
                }
            },
        }
    },
    # ── Dev (admin-only) ───────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "dev_index",
            "description": "בניית אינדקס של קוד המקור של פורטרס. חובה להשתמש בכלי הזה כשהמשתמש אומר 'אנדקס', 'index', 'תאנדקס', או 'תנתח את הקוד'. מנהל בלבד. העבר את התוצאה המלאה למשתמש.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "dev_query",
            "description": "שאילתה על מבנה הקוד — skills, services, models, tools. מנהל בלבד. העבר את התוצאה המלאה למשתמש.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "שאלה על מבנה הקוד"},
                    },
                    "required": ["question"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "dev_plan",
            "description": "תכנון פיצ׳ר חדש על בסיס ניתוח הקוד הקיים. מנהל בלבד.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "feature_request": {"type": "string", "description": "תיאור הפיצ׳ר הרצוי"},
                    },
                    "required": ["feature_request"],
                }
            },
        }
    },
]


def get_tool_schemas() -> list[ToolSchema]:
    """Return all tool schemas in Bedrock Converse toolConfig format."""
    return list(_TOOL_SCHEMAS)
