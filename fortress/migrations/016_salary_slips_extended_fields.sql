BEGIN;

-- Extended fields for richer agent context on salary slips
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS employee_id TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS employer_id TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS tax_file_number TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS job_start_date DATE;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS job_percentage DECIMAL;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS bank_account TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS bank_branch TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS bank_code TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS tax_bracket_percent DECIMAL;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS tax_credit_points DECIMAL;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS gross_for_tax DECIMAL;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS gross_for_national_insurance DECIMAL;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS marital_status TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS health_fund TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS pension_fund_name TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS education_fund_name TEXT;
ALTER TABLE salary_slips ADD COLUMN IF NOT EXISTS employee_address TEXT;

COMMIT;
