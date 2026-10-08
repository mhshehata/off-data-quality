ALTER TABLE staging.stg_product
ADD COLUMN IF NOT EXISTS barcode_valid boolean;