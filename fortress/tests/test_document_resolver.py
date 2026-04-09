from __future__ import annotations

from src.services.document_resolver import resolve_document


def test_resolve_electra_utility_bill_returns_canonical_match():
    raw_text = """
    עם חשמל ירוק של
    מספר צרכן אלקטרה פאוור: 377035963
    חיוב ₪ צריכה מאלקטרה פאוור
    חשבונית מס/קבלה (מקור) 55863951
    תאריך עריכת החשבון: 01/02/2026
    """

    match = resolve_document(raw_text, "55863951.pdf")

    assert match is not None
    assert match.doc_type == "electricity_bill"
    assert match.canonical_record_type == "utility_bill"
    assert match.canonical_routing_key == "utility_bill:electricity:electra_power"
    assert match.metadata["provider_slug"] == "electra_power"
    assert match.metadata["issuer_account_number"] == "377035963"
    assert match.metadata["issuer_bill_number"] == "55863951"
