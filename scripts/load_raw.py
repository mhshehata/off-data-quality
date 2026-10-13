import gzip
import json
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PATH = "data/openfoodfacts_products_1790749069_1790836258.json.gz"

path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
source_file = os.path.basename(path)

INSERT_GOOD = """
INSERT INTO raw_deltafiles.off_product (source_file, line_number, record)
VALUES (%s, %s, %s::jsonb)
ON CONFLICT (source_file, line_number) DO NOTHING
"""

INSERT_BAD = """
INSERT INTO raw_deltafiles.rejected_row (source_file, line_number, raw_record, reason)
VALUES (%s, %s, %s, %s)
ON CONFLICT (source_file, line_number) DO NOTHING
"""

read = 0
inserted = 0
rejected = 0

with psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", "5433")),
    dbname="offdq",
    user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    with conn.cursor() as cur:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                read += 1
                try:
                    json.loads(line)
                    cur.execute(INSERT_GOOD, (source_file, line_number, line))
                    inserted += cur.rowcount
                except json.JSONDecodeError as e:
                    cur.execute(INSERT_BAD, (source_file, line_number, line, str(e)))
                    rejected += cur.rowcount

print("read", read, "inserted", inserted, "rejected", rejected)