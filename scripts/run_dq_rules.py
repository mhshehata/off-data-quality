"""Run DQ rules on staging and write the failures to dq.dq_failure.

Rerun-safe: a failure is identified by (barcode, rule_id, rule_version, source_file).
A rerun updates existing failures, keeps their first detected_at, and removes
failures that no longer apply.

Rules here: R02 (barcode check, own function) and the completeness rules
(one table, one generic runner).
"""
import collections
import os

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from gtin import VALID_LENGTHS, gtin_check

load_dotenv()

RULE_VERSION = 1

UPSERT = """
INSERT INTO dq.dq_failure (barcode, rule_id, rule_version, source_file, field, evidence, reason)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (barcode, rule_id, rule_version, source_file) DO UPDATE SET
    field = EXCLUDED.field,
    evidence = EXCLUDED.evidence,
    reason = EXCLUDED.reason
"""

DELETE_STALE = """
DELETE FROM dq.dq_failure
WHERE rule_id = %s AND rule_version = %s AND source_file = %s
  AND barcode <> ALL(%s)
"""

# Completeness rules: rule ID -> (staging column, SQL condition that means "missing", reason).
# Text columns are NULL when empty (clean_text); tag lists can be NULL or an empty list.
COMPLETENESS_RULES = {
    "R03_missing_name": ("product_name", "product_name IS NULL", "Product name is missing"),
    "R04_missing_brand": ("brand_raw", "brand_raw IS NULL", "Brand is missing"),
    "R06_missing_category": (
        "categories", "categories IS NULL OR cardinality(categories) = 0", "No category"),
    "R09_missing_ingredients": (
        "ingredients_text", "ingredients_text IS NULL", "Ingredients text is missing"),
    "R10_missing_country": (
        "countries", "countries IS NULL OR cardinality(countries) = 0", "No country"),
    # nutrition_source is NULL when no usable as_sold per-100g/100ml set exists.
    # This also covers products with only per-serving sets; R12 will separate those.
    "R11_missing_nutrition": (
        "nutrition_source", "nutrition_source IS NULL", "No usable nutrition set"),
}


def write_failures(conn, rule_id, field, failures_by_file, source_files):
    """failures_by_file: {source_file: [(barcode, evidence, reason), ...]}.
    Upserts them and removes failures of this rule that no longer apply."""
    total = 0
    removed = 0
    for source_file in source_files:
        found = failures_by_file.get(source_file, [])
        for barcode, evidence, reason in found:
            conn.execute(UPSERT, (
                barcode, rule_id, RULE_VERSION, source_file, field, Jsonb(evidence), reason,
            ))
        total += len(found)
        cur = conn.execute(DELETE_STALE, (
            rule_id, RULE_VERSION, source_file, [b for b, _, _ in found]))
        removed += cur.rowcount
    return total, removed


# ---------- R02: invalid barcode ----------

R02_ID = "R02_invalid_barcode"


def r02_reason(evidence):
    kind = evidence["failure_type"]
    if kind == "non_digit":
        return "Barcode contains characters other than digits"
    if kind == "bad_length":
        lengths = ", ".join(str(n) for n in VALID_LENGTHS)
        return f"Barcode has {evidence['length']} digits, expected one of {lengths}"
    return (
        f"Check digit is {evidence['actual_check_digit']}, "
        f"expected {evidence['expected_check_digit']}"
    )


def r02_failures(rows):
    """rows: (source_file, barcode) tuples flagged invalid in staging.
    Returns {source_file: [(barcode, evidence, reason), ...]}."""
    result = collections.defaultdict(list)
    for source_file, barcode in rows:
        evidence = gtin_check(barcode)
        if evidence is None:
            continue  # staging says invalid but the check passes: should never happen
        result[source_file].append((barcode, evidence, r02_reason(evidence)))
    return result


def run_r02(conn, source_files):
    flagged = conn.execute("""
        SELECT source_file, barcode FROM staging.stg_product
        WHERE barcode_valid IS NOT TRUE
    """).fetchall()
    failures = r02_failures(flagged)
    total, removed = write_failures(conn, R02_ID, "barcode", failures, source_files)
    types = collections.Counter(
        e["failure_type"] for rows in failures.values() for _, e, _ in rows)
    print(f"{R02_ID}: {total} failures, {removed} stale removed, by type {dict(types)}")


# ---------- completeness rules ----------

def completeness_failures(rows, column, reason):
    """rows: (source_file, barcode) tuples where the field is missing."""
    result = collections.defaultdict(list)
    for source_file, barcode in rows:
        result[source_file].append((barcode, {"column": column, "state": "missing"}, reason))
    return result


def run_completeness(conn, source_files):
    for rule_id, (column, condition, reason) in COMPLETENESS_RULES.items():
        rows = conn.execute(
            f"SELECT source_file, barcode FROM staging.stg_product WHERE {condition}"
        ).fetchall()
        failures = completeness_failures(rows, column, reason)
        total, removed = write_failures(conn, rule_id, column, failures, source_files)
        print(f"{rule_id}: {total} failures, {removed} stale removed")


def main():
    with psycopg.connect(
        host="localhost", port=5433, dbname="offdq", user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        source_files = [r[0] for r in conn.execute(
            "SELECT DISTINCT source_file FROM staging.stg_product").fetchall()]
        run_r02(conn, source_files)
        run_completeness(conn, source_files)


if __name__ == "__main__":
    main()
