from __future__ import annotations
"""Fortress 2.0 PII Guard — regex-based detection, stripping, and restoration of Israeli PII."""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReplacementRecord:
    """A single PII replacement: original value, placeholder inserted, and pattern type."""

    original: str
    placeholder: str
    pattern_type: str


# Ordered patterns — credit cards first (longest spans), Israeli ID last (most generic).
_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}"), "[כרטיס]", "credit_card"),
    (re.compile(r"(?:\+?972)[2-9]\d{7,8}"), "[טלפון]", "phone"),
    (re.compile(r"0[2-9]\d{7,8}"), "[טלפון]", "phone"),
    (re.compile(r"[\w.-]+@[\w.-]+\.\w{2,}"), "[אימייל]", "email"),
    (re.compile(r"\d{2,3}[-/]\d{6,9}"), "[חשבון בנק]", "bank_account"),
    (re.compile(r"\b\d{9}\b"), "[ת.ז.]", "israeli_id"),
]


def strip_pii(text: str) -> tuple[str, list[ReplacementRecord]]:
    """Detect and replace PII in *text*.

    Returns ``(cleaned_text, records)`` where *records* is a list of
    :class:`ReplacementRecord` instances describing each replacement.
    When no PII is found the original text is returned unchanged with an
    empty list.
    """
    records: list[ReplacementRecord] = []
    # Track how many times each base placeholder has been used so far.
    placeholder_counts: dict[str, int] = {}

    for pattern, base_placeholder, pattern_type in _PII_PATTERNS:
        # Use a replacement function so we can build indexed placeholders.
        def _replacer(match: re.Match[str], _bp=base_placeholder, _pt=pattern_type) -> str:
            count = placeholder_counts.get(_bp, 0) + 1
            placeholder_counts[_bp] = count
            indexed = f"{_bp[:-1]}_{count}]"
            records.append(ReplacementRecord(original=match.group(), placeholder=indexed, pattern_type=_pt))
            return indexed

        text = pattern.sub(_replacer, text)

    if records:
        logger.info(
            "PII stripped: %d items (%s)",
            len(records),
            ", ".join(r.pattern_type for r in records),
        )

    return text, records


def restore_pii(text: str, records: list[ReplacementRecord]) -> str:
    """Replace indexed placeholders with original PII values from *records*.

    Returns the text unchanged when *records* is empty or no placeholders
    are found.
    """
    for record in records:
        text = text.replace(record.placeholder, record.original, 1)
    return text
