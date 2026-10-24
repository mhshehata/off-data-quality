-- Weekly scorecard KPIs. Read-only queries; run with psql.
-- A "week" is the ISO week of the delta file's window start, which is the
-- Unix epoch in the file name: openfoodfacts_products_<start>_<end>.json.gz

-- KPI 1: reconciliation and reject rate per delta file.
-- Invariant: raw_rows = staged_rows + rejected_rows on every line.
with raw as (
    select source_file, count(*) as raw_rows
    from raw_deltafiles.off_product
    group by source_file
),
stg as (
    select source_file, count(*) as staged_rows
    from staging.stg_product
    group by source_file
),
rej as (
    select source_file, count(*) as rejected_rows
    from raw_deltafiles.rejected_row
    group by source_file
)
select r.source_file,
       r.raw_rows,
       coalesce(s.staged_rows, 0)   as staged_rows,
       coalesce(j.rejected_rows, 0) as rejected_rows,
       round(100.0 * coalesce(j.rejected_rows, 0) / r.raw_rows, 4) as reject_rate_pct
from raw r
left join stg s using (source_file)
left join rej j using (source_file)
order by r.source_file;

-- KPI 2: rule failures per week by severity and dimension.
-- Only rules with counts_against_score = true are included. The critical rule
-- (R01, no barcode) rejects rows instead, so it shows up in KPI 1, not here.
-- failures_per_100_rows can exceed 100 (one row can fail several rules);
-- rows_affected_pct is the share of rows with at least one failure.
-- rows_affected must not be summed across dimensions (rows overlap).
with files as (
    select distinct source_file,
           date_trunc('week', to_timestamp(split_part(source_file, '_', 3)::bigint)) as week
    from staging.stg_product
),
checked as (
    select f.week, count(*) as staged_rows
    from staging.stg_product s
    join files f using (source_file)
    group by f.week
),
fails as (
    select f.week, r.severity, r.dimension,
           count(*) as failures,
           count(distinct (d.barcode, d.source_file)) as rows_affected
    from dq.dq_failure d
    join dq.dq_rule r using (rule_id, rule_version)
    join files f using (source_file)
    where r.counts_against_score
    group by f.week, r.severity, r.dimension
)
select f.week::date as week_start, f.severity, f.dimension,
       f.failures, f.rows_affected, c.staged_rows,
       round(100.0 * f.failures / c.staged_rows, 1)      as failures_per_100_rows,
       round(100.0 * f.rows_affected / c.staged_rows, 1) as rows_affected_pct
from fails f
join checked c using (week)
order by f.week desc, f.failures desc;
