import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
with psycopg.connect(host="localhost", port=5433, dbname="offdq", user="offdq",
                     password=os.environ["POSTGRES_PASSWORD"]) as conn:
    rows = conn.execute(
        "SELECT rule_id, source_file, count(*) FROM dq.dq_failure "
        "GROUP BY rule_id, source_file ORDER BY rule_id, source_file"
    ).fetchall()
for r in rows:
    print(r)