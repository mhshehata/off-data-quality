"""Run DQ rules on staging and write the failures to dq.dq_failure.

Rerun-safe: a failure is identified by (barcode, rule_id, rule_version, source_file).
A rerun updates existing failures, keeps their first detected_at, and removes
failures that no longer apply.

Rules here: R02 (barcode check, own function) and the SQL-condition rules
(completeness and value checks: one table, one generic runner).

Usage:
    python scripts/run_dq_rules.py                  all files in staging (full rerun,
                                                    needed after a rule changes)
    python scripts/run_dq_rules.py FILE [FILE ...]  only these source files (nightly run)
"""
import collections
import os
import sys

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
  AND barcode <> ALL(%s::text[])
"""

def missing(column, condition, reason):
    """Completeness rule: evidence says which column is missing."""
    evidence = f"jsonb_build_object('column', '{column}', 'state', 'missing')"
    return (column, condition, evidence, reason)


# Nutrition plausibility (staging holds one per-100g/100ml set, so these are per 100g/100ml).
# Thresholds follow Open Food Facts' own checks (DataQualityFood.pm): 3,911 kJ = 935 kcal,
# 105 g per nutrient, subset tolerance 0.01 g (0.1 g when the total is 10 g or more).
# The energy formula is our approximation: 9 fat + 4 carbs + 4 protein + 2 fibre (kcal/g).
COMPUTED_KCAL = "(9 * fat_g + 4 * carbs_g + 4 * proteins_g + 2 * COALESCE(fiber_g, 0))"
NUTRIENT_COLUMNS = ["fat_g", "saturated_fat_g", "carbs_g", "sugars_g", "proteins_g", "fiber_g"]
OVER_105 = " OR ".join(f"{c} > 105 OR {c} < 0" for c in NUTRIENT_COLUMNS)
MACRO_SUM = "COALESCE(fat_g, 0) + COALESCE(carbs_g, 0) + COALESCE(proteins_g, 0)"


# SQL-condition rules: rule ID -> (field, condition for a failure, evidence SQL, reason).
# The evidence SQL builds the JSON from the staging row, so it holds the observed values.
# Text columns are NULL when empty (clean_text); tag lists can be NULL or an empty list.
RULES = {
    "R03_missing_name": missing("product_name", "product_name IS NULL", "Product name is missing"),
    "R04_missing_brand": missing("brand_raw", "brand_raw IS NULL", "Brand is missing"),
    "R06_missing_category": missing(
        "categories", "categories IS NULL OR cardinality(categories) = 0", "No category"),
    "R09_missing_ingredients": missing(
        "ingredients_text", "ingredients_text IS NULL", "Ingredients text is missing"),
    "R10_missing_country": missing(
        "countries", "countries IS NULL OR cardinality(countries) = 0", "No country"),
    # nutrition_source is NULL when no usable as_sold per-100g/100ml set exists.
    # This also covers products with only per-serving sets; R12 will separate those.
    "R11_missing_nutrition": missing(
        "nutrition_source", "nutrition_source IS NULL", "No usable nutrition set"),
    "R07_unparsed_quantity": (
        "quantity_value",
        "quantity_text IS NOT NULL AND quantity_value IS NULL",
        "jsonb_build_object('quantity_text', quantity_text)",
        "Quantity text present but no numeric quantity",
    ),
    "R08_invalid_unit": (
        "quantity_unit",
        "quantity_unit IS NOT NULL AND quantity_unit NOT IN ('g', 'ml')",
        "jsonb_build_object('quantity_unit', quantity_unit)",
        "Quantity unit is not g or ml",
    ),
    "R21_future_timestamp": (
        "last_modified_at",
        "last_modified_at > now()",
        "jsonb_build_object('last_modified_at', last_modified_at)",
        "Last modified time is in the future",
    ),
    "R22_date_order": (
        "created_at",
        "created_at > last_modified_at",
        "jsonb_build_object('created_at', created_at, 'last_modified_at', last_modified_at)",
        "Created after last modified",
    ),
    "R13_estimated_nutrition": (
        "nutrition_source",
        "nutrition_source = 'estimate'",
        "jsonb_build_object('nutrition_source', nutrition_source)",
        "Nutrition values are an estimate, not from the manufacturer or the package",
    ),
    # Preferred basis: 100ml for ml products, 100g otherwise (STTM row 14).
    "R23_assumed_basis": (
        "nutrition_basis",
        "nutrition_source IS NOT NULL AND nutrition_basis <> "
        "CASE WHEN quantity_unit = 'ml' THEN '100ml' ELSE '100g' END",
        "jsonb_build_object('nutrition_basis', nutrition_basis, 'quantity_unit', quantity_unit)",
        "Nutrition basis is not the preferred one for this product's unit",
    ),
    "R15_impossible_energy": (
        "energy_kcal",
        "energy_kcal > 935 OR energy_kcal < 0",
        "jsonb_build_object('energy_kcal', energy_kcal, 'nutrition_basis', nutrition_basis)",
        "Energy is outside 0 to 935 kcal per 100g/ml",
    ),
    # Differs from OFF: the sum here leaves salt out, so a salt error shows up only in R17.
    "R16_impossible_nutrient": (
        "nutrients",
        f"({OVER_105}) OR ({MACRO_SUM}) > 105",
        "jsonb_build_object('fat_g', fat_g, 'saturated_fat_g', saturated_fat_g, "
        "'carbs_g', carbs_g, 'sugars_g', sugars_g, 'proteins_g', proteins_g, "
        "'fiber_g', fiber_g, 'fat_carbs_protein_sum', " + MACRO_SUM + ")",
        "A nutrient is outside 0 to 105 g per 100g/ml, or fat + carbs + protein exceeds 105 g",
    ),
    "R17_impossible_salt": (
        "salt_g",
        "salt_g > 105",
        "jsonb_build_object('salt_g', salt_g, 'salt_derived', salt_derived)",
        "Salt is above 105 g per 100g/ml",
    ),
    # Only when energy is above 13 kcal and fat, carbs and protein are all present.
    "R18_energy_macro_conflict": (
        "energy_kcal",
        "energy_kcal > 13 AND fat_g IS NOT NULL AND carbs_g IS NOT NULL "
        "AND proteins_g IS NOT NULL AND ("
        f"{COMPUTED_KCAL} < 0.7 * energy_kcal - 5 OR {COMPUTED_KCAL} > 1.3 * energy_kcal + 5)",
        "jsonb_build_object('energy_kcal', energy_kcal, 'computed_kcal', " + COMPUTED_KCAL + ")",
        "Stated energy does not match the energy computed from fat, carbs, protein and fibre",
    ),
    "R19_subset_conflict": (
        "nutrients",
        "sugars_g > carbs_g + CASE WHEN carbs_g >= 10 THEN 0.1 ELSE 0.01 END "
        "OR saturated_fat_g > fat_g + CASE WHEN fat_g >= 10 THEN 0.1 ELSE 0.01 END",
        "jsonb_build_object('sugars_g', sugars_g, 'carbs_g', carbs_g, "
        "'saturated_fat_g', saturated_fat_g, 'fat_g', fat_g)",
        "Sugars exceed carbohydrates, or saturated fat exceeds fat",
    ),
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
        WHERE barcode_valid IS NOT TRUE AND source_file = ANY(%s::text[])
    """, (source_files,)).fetchall()
    failures = r02_failures(flagged)
    total, removed = write_failures(conn, R02_ID, "barcode", failures, source_files)
    types = collections.Counter(
        e["failure_type"] for rows in failures.values() for _, e, _ in rows)
    print(f"{R02_ID}: {total} failures, {removed} stale removed, by type {dict(types)}")


# ---------- SQL-condition rules ----------

def run_sql_rules(conn, source_files):
    for rule_id, (field, condition, evidence_sql, reason) in RULES.items():
        rows = conn.execute(
            f"SELECT source_file, barcode, {evidence_sql} FROM staging.stg_product "
            f"WHERE ({condition}) AND source_file = ANY(%s::text[])",
            (source_files,),
        ).fetchall()
        failures = collections.defaultdict(list)
        for source_file, barcode, evidence in rows:
            failures[source_file].append((barcode, evidence, reason))
        total, removed = write_failures(conn, rule_id, field, failures, source_files)
        print(f"{rule_id}: {total} failures, {removed} stale removed")


def main():
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"), port=int(os.environ.get("POSTGRES_PORT", "5433")), dbname="offdq", user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        in_staging = {r[0] for r in conn.execute(
            "SELECT DISTINCT source_file FROM staging.stg_product").fetchall()}
        requested = sys.argv[1:]
        unknown = [f for f in requested if f not in in_staging]
        if unknown:
            sys.exit(f"not in staging, nothing was checked: {', '.join(unknown)}")
        source_files = requested or sorted(in_staging)
        print(f"checking {len(source_files)} file(s)")
        run_r02(conn, source_files)
        run_sql_rules(conn, source_files)


if __name__ == "__main__":
    main()
