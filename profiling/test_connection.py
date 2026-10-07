import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(
    host="localhost",
    port=5433,
    dbname="offdq",
    user="offdq",
    password=os.environ["POSTGRES_PASSWORD"],
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_database()")
        print(cur.fetchone())