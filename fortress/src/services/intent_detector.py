from __future__ import annotations

"""Lightweight intent guardrail for strict deterministic UX."""

import re

INTENT_DOCUMENTS = "documents"
INTENT_TASKS = "tasks"
INTENT_DOCUMENT_QUERY = "document_query"
INTENT_DELETE_DOCUMENTS = "delete_documents"
INTENT_UNKNOWN = "unknown"

_DELETE_DOCUMENTS_PATTERNS = [
    re.compile(r"נקה מסמכים", re.IGNORECASE),
    re.compile(r"מחק(?:י|ו)?\s+מסמכים", re.IGNORECASE),
    re.compile(r"מחק(?:י|ו)?\s+את כל המסמכים", re.IGNORECASE),
]

_DOCUMENT_QUERY_PATTERNS = [
    re.compile(r"^כמה.+(ביטוח|חשבונית|חוזה|מסמך|הסכם)", re.IGNORECASE),
    re.compile(r"^(תביא|תראה|מצא|תמצא)\s+לי\s+.+", re.IGNORECASE),
    re.compile(r"(מה הסכום|מה התאריך|מי הספק|תן לי סיכום)", re.IGNORECASE),
]

_DOCUMENT_LIST_PATTERNS = [
    re.compile(r"(מסמכים|רשימת מסמכים|איזה מסמכים|מה המסמכים)", re.IGNORECASE),
]

_TASK_PATTERNS = [
    re.compile(r"(משימ|tasks|to.?do|תזכור לי)", re.IGNORECASE),
]

_NON_SYSTEM_PATTERNS = [
    re.compile(r"(בדיחה|translate|תרגם|מה זה|who is|what is)", re.IGNORECASE),
]


def detect_intent(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return INTENT_UNKNOWN
    if any(p.search(text) for p in _DELETE_DOCUMENTS_PATTERNS):
        return INTENT_DELETE_DOCUMENTS
    if any(p.search(text) for p in _DOCUMENT_QUERY_PATTERNS):
        return INTENT_DOCUMENT_QUERY
    if any(p.search(text) for p in _DOCUMENT_LIST_PATTERNS):
        return INTENT_DOCUMENTS
    if any(p.search(text) for p in _TASK_PATTERNS):
        return INTENT_TASKS
    return INTENT_UNKNOWN


def should_fallback_to_chat(message: str) -> bool:
    """Allow ChatSkill only for clearly non-system queries."""
    text = (message or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _NON_SYSTEM_PATTERNS)

