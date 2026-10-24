-- Weekly scorecard snapshots, written by the n8n scorecard workflow.
-- One row per (week, kpi, detail). A week is the ISO week of the delta
-- file's window start. Re-running a week overwrites it (upsert on the key).
--
-- kpi values and what detail holds:
--   files_loaded           ''         number of delta files in the week (7 = complete week)
--   rows_staged            ''         staged rows in the week
--   rows_rejected          ''         rows rejected in the week (critical rule R01)
--   rows_affected_pct      dimension  % of staged rows failing at least one scored rule in it
--   rule_rows_affected_pct rule_id    % of staged rows failing that rule
create table if not exists ops.weekly_scorecard (
    week_start  date        not null,
    kpi         text        not null,
    detail      text        not null default '',
    value       numeric     not null,
    computed_at timestamptz not null default now(),
    primary key (week_start, kpi, detail)
);
