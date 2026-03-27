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


def phone_lookup_candidates(raw: str) -> list[str]:
    """Return normalized variants that may match the same person.

    This helps bridge WAHA/NOWEB identifiers such as ``@lid`` and stored DB
    values that may be saved with or without ``+`` or local ``05X`` format.
    """
    if not raw:
        return []

    normalized = normalize_phone(raw)
    if not normalized:
        return []

    candidates: list[str] = []
    for candidate in (
        raw,
        raw.split("@")[0],
        normalized,
        f"+{normalized}",
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    if normalized.startswith("972") and len(normalized) == 12:
        local = f"0{normalized[3:]}"
        for candidate in (local, f"+{local}"):
            if candidate not in candidates:
                candidates.append(candidate)

    if normalized.startswith("0") and len(normalized) == 10:
        international = f"972{normalized[1:]}"
        for candidate in (international, f"+{international}"):
            if candidate not in candidates:
                candidates.append(candidate)

    return candidates


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
