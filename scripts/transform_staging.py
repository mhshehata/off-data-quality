"""Transform raw_deltafiles.off_product into staging.stg_product.

Rules come from docs/sttm.xlsx (rows 1, 3-13, 24-28, 30). Barcode validity
(row 2) and nutrition (rows 14-23) are NOT done here yet.

Principle: a value that cannot be cleaned or cast becomes None (NULL).
The original record stays in the raw table, so nothing is lost.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SOURCE_FILE = "openfoodfacts_products_1790749069_1790836258.json.gz"


# ---------- cleaning functions (one job each, easy to test) ----------

def clean_text(value):
    """Trim, collapse repeated whitespace to one space; empty -> None."""
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def lower_text(value):
    cleaned = clean_text(value)
    return cleaned.lower() if cleaned else None


def to_number(value):
    """int/float pass through, numeric strings are cast, anything else -> None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def unix_to_timestamp(value):
    """UNIX seconds -> timezone-aware UTC datetime."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def strip_prefix(tag, prefix):
    if tag.startswith(prefix):
        return tag[len(prefix):]
    return tag


def clean_tags(values, prefix="en:"):
    """List of tags -> list with the prefix stripped; missing/not a list -> None."""
    if not isinstance(values, list):
        return None
    tags = [strip_prefix(v.strip(), prefix) for v in values if isinstance(v, str) and v.strip()]
    return tags


def first_brand(values):
    """brands_tags: first tag, language prefix like 'xx:' stripped."""
    tags = clean_tags(values, prefix="xx:")
    return tags[0] if tags else None


def is_valid_gtin(barcode):
    """R02: digits only, length 8/12/13/14, GTIN mod-10 check digit correct."""
    if not isinstance(barcode, str) or not barcode.isascii() or not barcode.isdigit():
        return False
    if len(barcode) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in barcode]
    check_digit = digits[-1]
    # Reverse the digits without the check digit; weights alternate 3, 1, 3, 1...
    body = digits[:-1][::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return (10 - total % 10) % 10 == check_digit


SOURCE_PRECEDENCE = ["manufacturer", "packaging", "estimate"]


def _best_set(sets, basis):
    """Among as_sold sets with this basis, the one with the best source (first on ties)."""
    candidates = [
        s for s in sets
        if isinstance(s, dict) and s.get("preparation") == "as_sold" and s.get("per") == basis
        and s.get("source") in SOURCE_PRECEDENCE
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda s: SOURCE_PRECEDENCE.index(s["source"]))


def select_nutrition_set(sets, quantity_unit):
    """Pick ONE nutrition set (STTM row 14).

    Preferred basis: 100ml if the unit is ml, otherwise 100g.
    Filter: as_sold and the preferred basis; then manufacturer > packaging > estimate.
    If nothing matches, repeat with the other basis (fallback, flagged later as R23).
    Returns the chosen set, or None.
    """
    if not isinstance(sets, list):
        return None
    preferred, other = ("100ml", "100g") if lower_text(quantity_unit) == "ml" else ("100g", "100ml")
    return _best_set(sets, preferred) or _best_set(sets, other)


# ---------- one raw record -> one staging row ----------

def transform(record):
    barcode = clean_text(record.get("code"))
    return {
        "barcode": barcode,
        "barcode_valid": is_valid_gtin(barcode),
        "product_name": clean_text(record.get("product_name")),
        "brand_raw": clean_text(record.get("brands")),
        "brand_normalised": first_brand(record.get("brands_tags")),
        "categories": clean_tags(record.get("categories_tags")),
        "quantity_text": clean_text(record.get("quantity")),
        "quantity_value": to_number(record.get("product_quantity")),
        "quantity_unit": lower_text(record.get("product_quantity_unit")),
        "serving_size": clean_text(record.get("serving_size")),
        "ingredients_text": clean_text(record.get("ingredients_text")),
        "labels": clean_tags(record.get("labels_tags")),
        "countries": clean_tags(record.get("countries_tags")),
        "last_modified_at": unix_to_timestamp(record.get("last_modified_t")),
        "created_at": unix_to_timestamp(record.get("created_t")),
        "last_editor": clean_text(record.get("last_editor")),
        "language": lower_text(record.get("lc")),
        "off_dq_errors": clean_tags(record.get("data_quality_errors_tags")),
        "off_states": clean_tags(record.get("states_tags")),
    }


COLUMNS = [
    "barcode", "barcode_valid", "product_name", "brand_raw", "brand_normalised", "categories",
    "quantity_text", "quantity_value", "quantity_unit", "serving_size",
    "ingredients_text", "labels", "countries", "last_modified_at", "created_at",
    "last_editor", "language", "off_dq_errors", "off_states",
]

# Rerun-safe. If a barcode already exists for this file, the row is replaced
# when the incoming version is newer or the same (>=), never when it is older. A repeat inside one file therefore
# keeps the newest last_modified_t.
UPSERT = f"""
INSERT INTO staging.stg_product (source_file, {", ".join(COLUMNS)})
VALUES (%(source_file)s, {", ".join("%(" + c + ")s" for c in COLUMNS)})
ON CONFLICT (source_file, barcode) DO UPDATE SET
    {", ".join(c + " = EXCLUDED." + c for c in COLUMNS if c != "barcode")},
    loaded_at = now()
WHERE staging.stg_product.last_modified_at IS NULL
   OR EXCLUDED.last_modified_at >= staging.stg_product.last_modified_at
"""

QUARANTINE = """
INSERT INTO raw_deltafiles.rejected_row (source_file, line_number, raw_record, reason)
VALUES (%s, %s, %s, %s)
ON CONFLICT (source_file, line_number) DO NOTHING
"""


def main():
    source_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE_FILE
    read = written = unchanged = quarantined = 0

    with psycopg.connect(
        host="localhost",
        port=5433,
        dbname="offdq",
        user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        with conn.cursor(name="raw_rows") as reader, conn.cursor() as writer:
            reader.itersize = 1000
            reader.execute(
                "SELECT line_number, record FROM raw_deltafiles.off_product "
                "WHERE source_file = %s ORDER BY line_number",
                (source_file,),
            )
            for line_number, record in reader:
                read += 1
                row = transform(record)
                if row["barcode"] is None:
                    writer.execute(
                        QUARANTINE,
                        (source_file, line_number, json.dumps(record), "R01: no barcode"),
                    )
                    quarantined += 1
                    continue
                row["source_file"] = source_file
                writer.execute(UPSERT, row)
                if writer.rowcount == 1:
                    written += 1
                else:
                    unchanged += 1

    print("read", read, "written", written, "unchanged", unchanged, "quarantined", quarantined)


if __name__ == "__main__":
    main()
