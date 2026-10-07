CREATE SCHEMA IF NOT EXISTS staging;

-- Typed staging layer, one row per product per delta file.
-- Columns follow docs/sttm.xlsx (rows 1, 3-13, 24-28, 30).
-- Everything except the key is nullable: a value that cannot be cast
-- becomes NULL here, and the original stays in raw_deltafiles.off_product.
-- Barcode validity (row 2) and nutrition (rows 14-23) come in a later step.
CREATE TABLE staging.stg_product (
    source_file       text         NOT NULL,
    barcode           text         NOT NULL,
    product_name      text,
    brand_raw         text,
    brand_normalised  text,
    categories        text[],
    quantity_text     text,
    quantity_value    numeric,
    quantity_unit     text,
    serving_size      text,
    ingredients_text  text,
    labels            text[],
    countries         text[],
    last_modified_at  timestamptz,
    created_at        timestamptz,
    last_editor       text,
    language          text,
    off_dq_errors     text[],
    off_states        text[],
    loaded_at         timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, barcode)
);
