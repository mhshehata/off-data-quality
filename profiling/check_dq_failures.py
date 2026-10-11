import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    print("by rule and type:", conn.execute("""
        SELECT rule_id, evidence->>'failure_type', count(*)
        FROM dq.dq_failure GROUP BY 1, 2 ORDER BY 1, 3 DESC
    """).fetchall())
    print("sample:", conn.execute("""
        SELECT barcode, reason FROM dq.dq_failure ORDER BY barcode LIMIT 5
    """).fetchall())
