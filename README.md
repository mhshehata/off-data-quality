# OFF Product Data Quality Pipeline


## Problem

Product data goes wrong in boring ways: a salt value of 720 g per 100 g, a quantity written as text but never turned into a number, nutrition facts missing altogether. Checking this manually when you have millions of entries does not make any sense. Open Food Facts publishes a new batch of products every day, and the one I profiled had 7,629 records, nearly a quarter with no nutrition data at all. This project checks every record against a written set of rules, stores each failure with its reason, and marks which ones could be fixed from data already in the record. A planned second step will let an AI suggest those fixes, with a person making the final call.

## Before: the manual baseline (an estimate)

I counted what one daily file would need and put a time on each kind of fix. The counts are measured from one real file (7,629 records). The minutes are assumptions.

| Kind of fix | Count | Time each | Total |
|---|---|---|---|
| Tier 1: fill a value from data already in the record | 429 | 10 s | about 1.2 h |
| Tier 2: a quick web check | 1,669 | 1 to 3 min (assumed) | about 28 to 84 h |
| Tier 3: package photo or product page | 4,963 | 1 to 3 min (assumed) | about 83 to 248 h |
| **Total** | | | **about 110 to 330 person-hours** |

By hand, only the quick fixes are practical.

## What it does

1. Downloads the daily delta file from Open Food Facts.
2. Loads every record as raw JSON into Postgres, with the file name and load time.
3. Flattens the fields I need into a typed staging table.
4. Checks every record against 23 written rules (R01 to R23), defined in `docs/sttm.xlsx`. 19 are implemented in code. 4 (R05, R12, R14, R20) are designed but not built.
5. Stores every failure with its reason. Records with no barcode go to a separate quarantine table.
6. Exposes the findings as a small star schema (SQL views in schema `mart`) and calculates quality KPIs in SQL.
7. n8n runs the pipeline daily at 00:03 (Berlin time) and logs failures to `ops.pipeline_error`. A second n8n workflow writes a weekly quality scorecard to `ops.weekly_scorecard`. There is no external alert; failures are checked in the n8n executions list.

A second repository (planned, not built yet) will add the AI step on top of the failures stored here.

## Architecture

```
Open Food Facts                 One VPS, Docker Compose
daily delta files               +--------------------------------------------------+
(static.openfoodfacts.org)      |                                                  |
        |                       |  n8n  --- every day 00:03 --- POST /run -->      |
        |                       |                                  pipeline        |
        +-------- download -----+------------------------------->  (Python)        |
                                |                                  fetch > load >  |
                                |                                  transform >     |
                                |                                  rules           |
                                |                                     |            |
                                |  Postgres 18  <---------------------+            |
                                |   raw_deltafiles  staging  dq  mart  ops         |
                                |                                                  |
                                |  n8n error workflow --> ops.pipeline_error       |
                                |  n8n weekly workflow (Tue 06:00) --> ops.weekly_scorecard
                                +--------------------------------------------------+
```

n8n only schedules and routes errors. All data work is Python in a separate container, which n8n calls over HTTP and which is under version control here. A failed stage stops the run, names itself in the response and returns an HTTP error, so n8n sees the failure.

Postgres schemas: `raw_deltafiles` (original JSON and rejected lines), `staging` (typed products), `dq` (rules and failures), `mart` (the star schema views), `ops` (pipeline errors and the weekly scorecard). The n8n workflows are exported in `workflows/`.

## Decisions and why

- **Daily delta files, not API scraping.** A file can be rerun on exactly the same input. An API call cannot.
- **Raw layer first, typed staging second.** The full original JSON is kept, so rules can change and rerun without downloading again.
- **Nutrition comes from `nutrition`, not `nutriments`.** In the file I profiled, `nutriments` exists in 29.9% of records and is filled in 0.0% of them.
- **One nutrition set per product.** As sold, per 100 g (100 ml for liquids), source order manufacturer, then packaging, then estimate. The source is stored. Per-serving values are not converted, because a serving size adds error.
- **Rules are written before code.** Each rule has a severity (1 critical, 15 important, 7 optional) and a separate fix suggestion. A check finds a problem. A fix repairs it. They are not the same thing.
- **I compare against Open Food Facts' own checks instead of rebuilding them.** I checked three of my rules against their code. R02 (barcode check digit) has no equivalent there. R18 and R19 overlap with their checks, at least partly.
- **No automatic fixes for identity or numbers.** Barcodes and nutrition values are never guessed. The design allows AI suggestions for only four rules (R04 to R07), using only text already in the record, with a person confirming each one. The AI step is not built yet.
- **Findings live in three tables.** `dq_rule` holds each rule once. `dq_failure` holds one row per rule hit per product, optional rules included, and rerunning the same file replaces its rows instead of duplicating them. `rejected_row` holds records with no barcode.
- **The star schema is a set of views, not a second load.** The fact is `dq_failure` and the lookups are derived from tables that already exist, so there is nothing extra to keep in sync or reconcile. The cost is that it is a read layer, not a separate warehouse.
- **Two repositories.** This one is the pipeline. A second, planned repository would read `dq_failure` and own everything about AI suggestions and review. It does not exist yet.

## Star schema

Four views in schema `mart`, defined in `sql/10_star_schema.sql`.

| View | One row is | Notes |
|---|---|---|
| `fact_rule_failure` | one product failing one rule version in one file | same grain as the unique key of `dq_failure` |
| `dim_rule` | one rule version | dimension, severity, whether it counts against the score |
| `dim_file` | one delta file | week, plus rows read, staged and rejected: the denominator for any rate |
| `dim_product` | one barcode | latest version only; earlier attribute values are overwritten |

The fact holds failures only, so it cannot give a rate by itself. The row counts on `dim_file` supply the denominator.

Checks: 0 fact rows without a matching product, file or rule, and the star reproduces the weekly scorecard for the week of 12 October 2026 exactly (completeness 63.78%, consistency 4.82%, validity 0.38% of rows affected).

```sql
select fi.week_start, r.dimension,
       count(distinct (f.barcode, f.source_file)) as rows_affected
from mart.fact_rule_failure f
join mart.dim_rule r using (rule_id, rule_version)
join mart.dim_file fi using (source_file)
where r.counts_against_score
group by 1, 2
order by 1, 2;
```

## Failure modes handled

| What goes wrong | What happens | Status |
|---|---|---|
| The same file is loaded twice | Raw rows have a primary key on file and line number and are inserted with `ON CONFLICT DO NOTHING`. Staging is an upsert on file and barcode. Failures are an upsert on barcode, rule, rule version and file, and stale ones are deleted. | Tested: a second load read 7,629 lines and inserted 0. A second full run returned `nothing_new`. |
| A record has no barcode | Rule R01: the record goes to `rejected_row` with its line number and the reason, and is not staged. | Tested on real data: 4 rows over 26 files. |
| A line is not valid JSON | The line goes to `rejected_row` with the parser's error and the load continues. | In the code. No such line has appeared in real data yet, so this path is untested. |
| Rows go missing between stages | For every file, raw rows = staged rows + rejected rows. `mart.dim_file` makes this a one-line query. | Tested on all 26 files. |
| A stage fails partway | The run stops, names the failed stage and returns HTTP 500. The n8n error workflow writes the failure to `ops.pipeline_error`. A file counts as loaded only once it is in staging, so the next run picks it up again. | In the code. The error workflow has only been run with n8n sample data, not a real failure. A deliberate-breakage test is still to do. |
| A download is cut off | The file is written as `.part` and renamed only when complete, so a half file is never loaded. | In the code, not tested. |
| Two runs overlap | The second call gets HTTP 409 `busy` and does nothing. | In the code, not tested. |

Known gaps: there is no alert outside n8n (failures are read from the executions list and `ops.pipeline_error`). The rules stage re-checks every staged file on every run, so it gets slower each day. Downloaded files are never deleted. Four designed rules (R05, R12, R14, R20) have no code yet. See `docs/runbook.md` for what to do when something fails.

## Results (rows in, rows out, rows rejected)

Measured on the VPS after loading 26 daily delta files. The first file opens on 28 September 2026.

| Stage | Rows |
|---|---|
| Raw records loaded | 176,879 |
| Staged | 176,875 |
| Rejected (R01, no barcode) | 4 |

176,875 + 4 = 176,879, so every raw record ends up either staged or quarantined. None disappear. The same check holds for each of the 26 files individually.

Speed: one daily file end to end (download, load, transform and the 18 rules implemented at the time) took 45 seconds. Nine files plus one rules pass took 4 minutes 30 seconds. The rules pass re-checks every file already in staging, so this time will grow each day until the rules take a source-file argument.

## Setup

You need Docker or a Postgres 18 database, and Python 3.12.

1. Create a Postgres database `offdq` with a user `offdq`. These names are fixed in the scripts.
2. Create a `.env` file with `POSTGRES_PASSWORD`. The scripts connect to `localhost:5433` by default; set `POSTGRES_HOST` and `POSTGRES_PORT` to change that. `.env` is git-ignored.
3. `pip install -r requirements.txt`
4. Create the tables and views, in order: `python scripts/run_sql.py sql/01_raw.sql`, then `02`, `03`, `04`, `05`, `06`, `07`, `09`, `10`. (`sql/08_weekly_kpis.sql` holds read-only queries to run with `psql`.)
5. `python scripts/load_dq_rules.py` loads the rule catalogue from `docs/sttm.xlsx`.
6. `python scripts/run_pipeline.py` downloads every delta file in the Open Food Facts index that is not loaded yet, oldest first, and runs all stages. To start small, use `python scripts/run_pipeline.py --max 2`. Each file is about 30 MB.

To run it on a schedule, the `Dockerfile` builds the pipeline container (gunicorn on port 5001, endpoint `POST /run`). The Compose file for my server holds host-specific settings and is not in this repository. In n8n, import the three files from `workflows/`, attach your own Postgres credential to the Postgres nodes, and set the error workflow of the daily and weekly workflows to the imported error handler. The exports contain the ID of my instance's error handler, so it has to be re-selected. The schedules use the n8n instance timezone (Europe/Berlin on mine).

## Data and licence

This project uses data from [Open Food Facts](https://openfoodfacts.org), available under the Open Database License (ODbL), with individual contents under the Database Contents License (DbCL). `docs/sample_500.csv` is an extract of that data and stays under the same licences. Raw delta files are not included in this repository.
