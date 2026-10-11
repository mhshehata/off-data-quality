"""Run DQ rules on staging and write the failures to dq.dq_failure.

Rerun-safe: a failure is identified by (barcode, rule_id, rule_version, source_file).
A rerun updates existing failures, keeps their first detected_at, and removes
failures that no longer apply.
"""
import collections
import os

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from gtin import VALID_LENGTHS, gtin_check

load_dotenv()

R02_ID = "R02_invalid_barcode"
R02_VERSION = 1

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


def run_r02(conn):
    source_files = [r[0] for r in conn.execute(
        "SELECT DISTINCT source_file FROM staging.stg_product").fetchall()]
    flagged = conn.execute("""
        SELECT source_file, barcode FROM staging.stg_product
        WHERE barcode_valid IS NOT TRUE
    """).fetchall()
    failures = r02_failures(flagged)

    types = collections.Counter()
    removed = 0
    for source_file in source_files:
        found = failures.get(source_file, [])
        for barcode, evidence, reason in found:
            conn.execute(UPSERT, (
                barcode, R02_ID, R02_VERSION, source_file, "barcode", Jsonb(evidence), reason,
            ))
            types[evidence["failure_type"]] += 1
        cur = conn.execute(DELETE_STALE, (
            R02_ID, R02_VERSION, source_file, [b for b, _, _ in found]))
        removed += cur.rowcount
    print(f"{R02_ID}: {sum(types.values())} failures, {removed} stale removed, by type {dict(types)}")


def main():
    with psycopg.connect(
        host="localhost", port=5433, dbname="offdq", user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        run_r02(conn)


if __name__ == "__main__":
    main()
