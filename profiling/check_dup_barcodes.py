import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    rows = conn.execute("""
        SELECT record->>'code', count(*)
        FROM raw_deltafiles.off_product
        GROUP BY 1 HAVING count(*) > 1
        LIMIT 10
    """).fetchall()

print("duplicate barcodes:", rows)