DELETE FROM utility_bills WHERE document_id IN (SELECT id FROM documents WHERE doc_type = 'electricity_bill');
DELETE FROM document_facts WHERE document_id IN (SELECT id FROM documents WHERE doc_type = 'electricity_bill');
DELETE FROM documents WHERE doc_type = 'electricity_bill';
