BEGIN;

-- Extended fields for richer agent context on utility bills
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS total_with_vat DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS vat_amount DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS consumption_kwh DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS payment_due_date DATE;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS payment_method TEXT;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS meter_number TEXT;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS tariff_plan TEXT;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS contract_number TEXT;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS fixed_charges DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS kva_charge DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS savings_this_bill DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS savings_cumulative DECIMAL;
ALTER TABLE utility_bills ADD COLUMN IF NOT EXISTS service_address TEXT;

COMMIT;
