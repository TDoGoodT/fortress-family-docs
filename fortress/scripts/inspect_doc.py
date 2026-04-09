"""Inspect a processed document by ID."""
import sys
from src.database import get_db
from src.models.schema import Document, DocumentFact, SalarySlip

doc_id = sys.argv[1] if len(sys.argv) > 1 else "4b0f80d4-9f24-4d4d-94b2-7dad89dfc481"
db = next(get_db())
doc = db.query(Document).filter(Document.id == doc_id).first()
if not doc:
    print(f"Document {doc_id} not found")
    sys.exit(1)

print("=== DOCUMENT ===")
print(f"filename: {doc.original_filename}")
print(f"doc_type: {doc.doc_type}")
print(f"vendor: {doc.vendor}")
print(f"amount: {doc.amount}")
print(f"doc_date: {doc.doc_date}")
print(f"review_state: {doc.review_state}")
print(f"confidence: {doc.confidence}")
print(f"display_name: {doc.display_name}")
print(f"metadata: {doc.doc_metadata}")
print()
print("=== RAW TEXT ===")
print(doc.raw_text[:3000] if doc.raw_text else "NONE")
print()
print("=== FACTS ===")
facts = db.query(DocumentFact).filter(DocumentFact.document_id == doc.id).all()
for f in facts:
    print(f"  {f.fact_key} = {f.fact_value} (confidence={f.confidence}, type={f.fact_type})")
print()
print("=== SALARY SLIP ===")
slip = db.query(SalarySlip).filter(SalarySlip.document_id == doc.id).first()
if slip:
    print(f"  pay_year={slip.pay_year} pay_month={slip.pay_month}")
    print(f"  employer={slip.employer_name}")
    print(f"  employee={slip.employee_name}")
    print(f"  gross={slip.gross_salary} net={slip.net_salary} net_to_pay={slip.net_to_pay}")
    print(f"  total_deductions={slip.total_deductions}")
    print(f"  income_tax={slip.income_tax} ni={slip.national_insurance} health={slip.health_tax}")
    print(f"  pension_employee={slip.pension_employee} pension_employer={slip.pension_employer}")
    print(f"  review_state={slip.review_state} review_reason={slip.review_reason}")
    print(f"  extraction_model={slip.extraction_model}")
else:
    print("  NO SALARY SLIP RECORD")
