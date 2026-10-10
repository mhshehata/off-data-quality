-- Nutrition columns for staging.stg_product (STTM rows 14-20).
-- All mass nutrients are stored in grams per nutrition_basis (100g or 100ml);
-- energy is in kcal. Values in mg or ug in the source are converted in the loader.
ALTER TABLE staging.stg_product
    ADD COLUMN IF NOT EXISTS nutrition_source  text,
    ADD COLUMN IF NOT EXISTS nutrition_basis   text,
    ADD COLUMN IF NOT EXISTS energy_kcal       numeric,
    ADD COLUMN IF NOT EXISTS fat_g             numeric,
    ADD COLUMN IF NOT EXISTS saturated_fat_g   numeric,
    ADD COLUMN IF NOT EXISTS carbs_g           numeric,
    ADD COLUMN IF NOT EXISTS sugars_g          numeric,
    ADD COLUMN IF NOT EXISTS proteins_g        numeric,
    ADD COLUMN IF NOT EXISTS fiber_g           numeric,
    ADD COLUMN IF NOT EXISTS salt_g            numeric,
    ADD COLUMN IF NOT EXISTS salt_derived      boolean;
