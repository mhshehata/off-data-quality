# Runbook: OFF data quality pipeline

For whoever is on duty. It says what runs, how to tell it is healthy, and what to do for each known failure. Commands run from the directory that holds `compose.yaml` on the server.

## What runs

| What | When | Where |
|---|---|---|
| `OFF DQ daily pipeline` (n8n) calls `POST /run` on the pipeline container | daily 00:03, Europe/Berlin | stages: fetch, load, transform, rules |
| `OFF DQ weekly scorecard` (n8n) writes last week's KPIs to `ops.weekly_scorecard` | Tuesday 06:00 | needs Monday's last file loaded by the Tuesday 00:03 run |
| `OFF DQ error handler` (n8n) writes failed runs to `ops.pipeline_error` | on any failure of the two above | there is no email or chat alert |

## Daily check (2 minutes)

Failures and the last load. Run it as: `docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off' <<'SQL' ... SQL`

```sql
select logged_at, workflow_name, last_node, error_message
from ops.pipeline_error order by logged_at desc limit 5;

select max(source_file) as latest_file, max(loaded_at) as loaded_at
from staging.stg_product;

-- expect zero rows: every file must balance
select source_file, raw_rows, staged_rows, rejected_rows
from mart.dim_file
where raw_rows <> staged_rows + rejected_rows;
```

Also open Executions in n8n: the last `OFF DQ daily pipeline` run should be green. A green run with `{"status":"nothing_new"}` is normal when no new delta file exists.

## When something fails

Every stage is safe to run again. Rerun by opening `OFF DQ daily pipeline` in n8n and choosing Execute workflow. Read the pipeline log first: `docker compose logs --tail 100 pipeline` shows which stage failed (`[fetch]`, `[load]`, `[transform]` or `[rules]`).

| Symptom | Likely cause | Action |
|---|---|---|
| A row in `ops.pipeline_error`, stage `fetch` | Open Food Facts or the database was unreachable | Wait, then rerun. Nothing was changed. |
| Stage `load` or `transform` failed | Bad file, database error or disk full | Read the log, fix the cause, rerun. The file is picked up again because it is not in staging yet. Loads and upserts do not create duplicates. |
| Stage `rules` failed | Database error or a rule bug | Fix, rerun. Failures are upserted and stale ones deleted, so reruns do not duplicate. |
| The run returned HTTP 409 `busy` | A run is already in progress | Do not start another. Wait and check the log. |
| n8n shows a timeout but the log is still moving | n8n waits 10 minutes, the pipeline up to 1 hour (a large catch-up) | Let it finish. Check the log and `mart.dim_file`. Do not trigger again while it runs. |
| The reconciliation query returns rows (invalid JSON lines do not count here; see `invalid_json_lines` in `mart.dim_file`) | A file was only partly processed | Rerun the pipeline. If the file still does not balance, check its rows in `raw_deltafiles.rejected_row` and `staging.stg_product`. |
| No scorecard row for last week | The Tuesday run happened before the last file loaded, or it failed | Check `ops.pipeline_error`, then run `OFF DQ weekly scorecard` manually before the following Monday. It upserts, so a second run is safe. It always computes the previous calendar week relative to today. |

## Known gaps

- No alert outside n8n. Check Executions and `ops.pipeline_error`.
- The nightly rules stage checks only new files (about 8 s per file). After changing a rule, run a full re-check by hand: `docker compose exec -T pipeline python scripts/run_dq_rules.py` (about 2 min at 28 files, growing with file count).
- A successful run deletes the files it downloaded from `data/`; a failed run keeps them for inspection. Leftover `.part` files from a cut-off download are not cleaned up.
- No backup outside the server. The only backup so far is a manual `pg_dump -Fc` taken before an OS upgrade.
- Disk will fill. After 26 files the database was 2.3 GB (about 13 KB per row), and each delta file adds about 30 MB on top of the database growth. At roughly 7,600 records a day the 19 GB disk fills in about two months (my estimate). Check `df -h /` weekly until retention is added.
- Rules R05, R12, R14 and R20 are designed but not implemented.
