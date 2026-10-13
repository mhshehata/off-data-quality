import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

path = sys.argv[1]
sql = open(path, encoding="utf-8").read()

with psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", "5433")),
    dbname="offdq",
    user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    conn.execute(sql)

print("ran", path)