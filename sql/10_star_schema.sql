-- Small star schema over the DQ tables. All objects are views, so they are
-- rerun-safe and always current. Grain of the fact: one product failing one
-- rule version in one delta file (same as the unique key of dq.dq_failure).
-- dim_file carries the row counts, which are the denominator for any rate.
-- dim_product keeps the latest version per barcode (Type 1, history overwritten).
-- Week = date_trunc('week') of the file window start, same as 08_weekly_kpis.sql.
CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.dim_rule AS
SELECT rule_id, rule_version, dimension, severity, counts_against_score
FROM dq.dq_rule;

CREATE OR REPLACE VIEW mart.dim_file AS
WITH raw AS (
    SELECT source_file, count(*) AS raw_rows
    FROM raw_deltafiles.off_product GROUP BY source_file
),
stg AS (
    SELECT source_file, count(*) AS staged_rows
    FROM staging.stg_product GROUP BY source_file
),
rej AS (
    SELECT source_file, count(*) AS rejected_rows
    FROM raw_deltafiles.rejected_row GROUP BY source_file
)
SELECT r.source_file,
       to_timestamp(split_part(r.source_file, '_', 3)::bigint) AS window_start,
       date_trunc('week', to_timestamp(split_part(r.source_file, '_', 3)::bigint))::date AS week_start,
       r.raw_rows,
       coalesce(s.staged_rows, 0)   AS staged_rows,
       coalesce(j.rejected_rows, 0) AS rejected_rows
FROM raw r
LEFT JOIN stg s USING (source_file)
LEFT JOIN rej j USING (source_file);

CREATE OR REPLACE VIEW mart.dim_product AS
SELECT DISTINCT ON (barcode)
       barcode, product_name, brand_normalised, brand_raw,
       categories, countries, last_modified_at
FROM staging.stg_product
ORDER BY barcode, last_modified_at DESC NULLS LAST, source_file DESC;

CREATE OR REPLACE VIEW mart.fact_rule_failure AS
SELECT failure_id, barcode, rule_id, rule_version, source_file,
       field, reason, detected_at
FROM dq.dq_failure;
