# OFF Product Data Quality Pipeline


## Problem

Product data goes wrong in boring ways: a salt value of 720 g per 100 g, a quantity written as text but never turned into a number, nutrition facts missing altogether. Checking this manually when you have millions of entries does not make any sense. Open Food Facts publishes a new batch of products every day, and the one I profiled had 7,629 records, nearly a quarter with no nutrition data at all. This project checks every record against a written set of rules, stores each failure with its reason, and sends only the fixable ones to an AI step, where a person still makes the final call.

## Before: the manual baseline (an estimate)

I counted what one daily file would need and put a time on each kind of fix. The counts are measured from one real file (7,629 records). The minutes are assumptions.

| Kind of fix | Count | Time each | Total |
|---|---|---|---|
| Tier 1: fill a value from data already in the record | 429 | 10 s | about 1.2 h |
| Tier 2: a quick web check | 1,669 | 1 to 3 min (assumed) | about 28 to 84 h |
| Tier 3: package photo or product page | 4,963 | 1 to 3 min (assumed) | about 83 to 248 h |
| **Total** | | | **about 110 to 330 person-hours** |

By hand, only the quick fixes are practical. The "after" number goes here once the pipeline has run.

## What it does

1. Downloads the daily delta file from Open Food Facts.
2. Loads every record as raw JSON into Postgres, with the file name and load time.
3. Flattens the fields I need into a typed staging table.
4. Checks every record against 22 written rules (R01 to R22), defined in `docs/sttm.xlsx`.
5. Stores every failure with its reason. Records with no barcode go to a separate quarantine table.
6. Loads validated records into a small star schema and calculates quality KPIs in SQL.
7. n8n runs it on a schedule, handles errors and sends a weekly quality scorecard.

A second repository (link to follow) adds the AI step on top of the failures stored here.

## Architecture

Diagram and n8n canvas screenshot to follow once the first full run works.

## Decisions and why

- **Daily delta files, not API scraping.** A file can be rerun on exactly the same input. An API call cannot.
- **Raw layer first, typed staging second.** The full original JSON is kept, so rules can change and rerun without downloading again.
- **Nutrition comes from `nutrition`, not `nutriments`.** In the file I profiled, `nutriments` exists in 29.9% of records and is filled in 0.0% of them.
- **One nutrition set per product.** As sold, per 100 g (100 ml for liquids), source order manufacturer, then packaging, then estimate. The source is stored. Per-serving values are not converted, because a serving size adds error.
- **Rules are written before code.** Each rule has a severity (1 critical, 16 important, 5 optional) and a separate fix suggestion. A check finds a problem. A fix repairs it. They are not the same thing.
- **I compare against Open Food Facts' own checks instead of rebuilding them.** I checked three of my rules against their code. R02 (barcode check digit) has no equivalent there. R18 and R19 overlap with their checks, at least partly.
- **No automatic fixes for identity or numbers.** Barcodes and nutrition values are never guessed. Only four rules (R04 to R07) are open to AI suggestions, using only text already in the record, and a person confirms each one.
- **Findings live in three tables.** `dq_rule` holds each rule once. `dq_failure` holds one row per rule hit per product, optional rules included, and rerunning the same file replaces its rows instead of duplicating them. `rejected_row` holds records with no barcode.
- **Two repositories.** This one is the pipeline. The second reads `dq_failure` and owns everything about AI suggestions and review.

## Failure modes handled

To follow, as each one is built and tested.

## Results (rows in, rows out, rows rejected)

Not run yet. Numbers go here after the first full run.

## Setup

To follow after the first full run.

## Data and licence

This project uses data from [Open Food Facts](https://openfoodfacts.org), available under the Open Database License (ODbL), with individual contents under the Database Contents License (DbCL). `docs/sample_500.csv` is an extract of that data and stays under the same licences. Raw delta files are not included in this repository.
