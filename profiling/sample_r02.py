import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    print("length x type:", conn.execute("""
        SELECT length(barcode), evidence->>'failure_type', count(*)
        FROM dq.dq_failure WHERE rule_id = 'R02_invalid_barcode'
        GROUP BY 1, 2 ORDER BY 3 DESC
    """).fetchall())
    print("starts with 0 / not:", conn.execute("""
        SELECT barcode LIKE '0%', count(*)
        FROM dq.dq_failure WHERE rule_id = 'R02_invalid_barcode' GROUP BY 1
    """).fetchall())
    print("20-row sample (fixed order, md5 of barcode):")
    for row in conn.execute("""
        SELECT f.barcode, f.reason, s.product_name, s.brand_normalised
        FROM dq.dq_failure f
        JOIN staging.stg_product s ON s.barcode = f.barcode AND s.source_file = f.source_file
        WHERE f.rule_id = 'R02_invalid_barcode'
        ORDER BY md5(f.barcode) LIMIT 20
    """).fetchall():
        print(row)
