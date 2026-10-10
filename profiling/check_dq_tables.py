import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost", port=5433, dbname="offdq", user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    print("tables:", conn.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'dq' ORDER BY 1
    """).fetchall())
    print("rows:", conn.execute("""
        SELECT (SELECT count(*) FROM dq.dq_rule), (SELECT count(*) FROM dq.dq_failure)
    """).fetchone())
