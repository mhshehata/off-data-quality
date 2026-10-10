import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    rows = conn.execute("""
        SELECT barcode, product_name, salt_g, salt_derived, nutrition_source
        FROM staging.stg_product
        WHERE salt_g > 25
        ORDER BY salt_g DESC
        LIMIT 10
    """).fetchall()

for row in rows:
    print(row)