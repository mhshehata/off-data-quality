import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    print("total products:", conn.execute("SELECT count(*) FROM staging.stg_product").fetchone())
    print("countries NULL / empty array / filled:", conn.execute("""
        SELECT count(*) FILTER (WHERE countries IS NULL),
               count(*) FILTER (WHERE countries IS NOT NULL AND cardinality(countries) = 0),
               count(*) FILTER (WHERE cardinality(countries) > 0)
        FROM staging.stg_product
    """).fetchone())
    print("the failing rows:", conn.execute("""
        SELECT barcode, product_name, last_editor
        FROM staging.stg_product
        WHERE countries IS NULL OR cardinality(countries) = 0
        ORDER BY barcode
    """).fetchall())
