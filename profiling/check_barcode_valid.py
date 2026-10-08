import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    rows = conn.execute("""
        SELECT barcode_valid, count(*)
        FROM staging.stg_product
        GROUP BY 1
        ORDER BY 1
    """).fetchall()

print(rows)