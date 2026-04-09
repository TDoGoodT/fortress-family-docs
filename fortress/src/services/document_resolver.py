"""Deterministic document resolver for stable canonical routing.

This layer sits before generic classification and is meant to scale to many
document families. Each resolver can:
- identify a document family using stable issuer/layout fingerprints
- assign a canonical doc_type for downstream extraction
- emit canonical routing metadata so weak extraction does not fork storage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import re


@dataclass(frozen=True)
class ResolverMatch:
    doc_type: str
    confidence: float
    canonical_record_type: str
    canonical_routing_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ResolverSpec:
    name: str
    doc_type: str
    canonical_record_type: str
    canonical_routing_key: str
    confidence: float
    markers: tuple[str, ...]
    builder: Optional[Callable[[str, str], dict[str, Any]]] = None


def _extract_first_group(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        for group in match.groups():
            if group:
                value = str(group).strip()
                if value:
                    return value
    return None


def _build_electra_utility_metadata(raw_text: str, filename: str) -> dict[str, Any]:
    issue_date = _extract_first_group(
        [
            r"תאריך\s+עריכת\s+הח(?:ש|ע)בון\s*[:：]?\s*([0-9]{2}[./][0-9]{2}[./][0-9]{4})",
        ],
        raw_text,
    )
    period_match = re.search(
        r"([0-9]{2}[./][0-9]{2}[./][0-9]{4})\s+([0-9]{2}[./][0-9]{2}[./][0-9]{4})",
        raw_text,
    )
    return {
        "provider_slug": "electra_power",
        "provider_name": "אלקטרה פאוור",
        "service_type": "electricity",
        "resolver_name": "electra_utility_bill",
        "issuer_account_number": _extract_first_group(
            [r"מספר\s+צרכן\s+אלקטרה(?:\s+פאוור)?\s*[:：]?\s*([0-9]{5,})"],
            raw_text,
        ),
        "issuer_bill_number": _extract_first_group(
            [
                r"חשבונית\s+מס/?קבלה\s*\(?.{0,20}?\)?\s*([0-9]{5,})",
                r"חשבונית\s+מס/?קבלה.*?([0-9]{5,})",
            ],
            raw_text,
        ) or re.sub(r"\..*$", "", filename),
        "issuer_issue_date": issue_date,
        "issuer_period_end": period_match.group(1) if period_match else None,
        "issuer_period_start": period_match.group(2) if period_match else None,
    }


_RESOLVERS: tuple[_ResolverSpec, ...] = (
    _ResolverSpec(
        name="electra_utility_bill",
        doc_type="electricity_bill",
        canonical_record_type="utility_bill",
        canonical_routing_key="utility_bill:electricity:electra_power",
        confidence=0.95,
        markers=(
            "מספר צרכן אלקטרה",
            "צריכה מאלקטרה",
            "עם חשמל ירוק",
            "super-power.co.il",
            "אלקטרה פאוור",
        ),
        builder=_build_electra_utility_metadata,
    ),
)


def resolve_document(raw_text: str, filename: str) -> ResolverMatch | None:
    haystack = f"{filename}\n{raw_text or ''}".lower()
    for spec in _RESOLVERS:
        if all(marker.lower() in haystack for marker in spec.markers[:2]) and any(
            marker.lower() in haystack for marker in spec.markers[2:]
        ):
            metadata = spec.builder(raw_text, filename) if spec.builder else {}
            return ResolverMatch(
                doc_type=spec.doc_type,
                confidence=spec.confidence,
                canonical_record_type=spec.canonical_record_type,
                canonical_routing_key=spec.canonical_routing_key,
                metadata=metadata,
            )
    return None
