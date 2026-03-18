"""Fortress 2.0 phone number utilities."""

import re


def normalize_phone(raw: str) -> str:
    """Normalize a phone number by stripping @c.us, non-digits, and leading +.

    Examples:
        "972501234567@c.us" → "972501234567"
        "+972-50-123-4567"  → "972501234567"
        "0501234567"        → "0501234567"
    """
    phone = raw.split("@")[0]
    phone = phone.lstrip("+")
    phone = re.sub(r"\D", "", phone)
    return phone


def is_valid_israeli_phone(phone: str) -> bool:
    """Return True if *phone* looks like a valid Israeli number.

    Valid formats:
        - Starts with "972" and has 12 digits total
        - Starts with "0" and has 10 digits total
    """
    if not phone.isdigit():
        return False
    if phone.startswith("972") and len(phone) == 12:
        return True
    if phone.startswith("0") and len(phone) == 10:
        return True
    return False
