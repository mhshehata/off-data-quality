import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    print("by source:", conn.execute("""
        SELECT nutrition_source, count(*) FROM staging.stg_product
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall())
    print("filled:", conn.execute("""
        SELECT count(energy_kcal), count(salt_g), count(fiber_g),
               count(*) FILTER (WHERE salt_derived)
        FROM staging.stg_product
    """).fetchone())
    print("max salt_g:", conn.execute("SELECT max(salt_g) FROM staging.stg_product").fetchone())
