"""Download OFF delta files that are not in staging yet, oldest first.

Prints one local path per file on stdout (nothing if all are loaded).
Usage: python scripts/fetch_delta.py [--dry-run] [--max N]
"""
import os
import re
import sys
import urllib.request

import psycopg
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://static.openfoodfacts.org/data/delta/"
FILE_PATTERN = re.compile(r"openfoodfacts_products_(\d+)_(\d+)\.json\.gz")
DATA_DIR = "data"


def list_remote_files():
    """File names from index.txt, oldest first (sorted by the start timestamp in the name)."""
    with urllib.request.urlopen(BASE_URL + "index.txt", timeout=30) as response:
        text = response.read().decode("utf-8")
    names = set()
    for line in text.splitlines():
        match = FILE_PATTERN.search(line)
        if match:
            names.add(match.group(0))
    return sorted(names, key=lambda n: int(FILE_PATTERN.match(n).group(1)))


def list_loaded_files():
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"), port=int(os.environ.get("POSTGRES_PORT", "5433")), dbname="offdq", user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        rows = conn.execute("SELECT DISTINCT source_file FROM staging.stg_product").fetchall()
    return {r[0] for r in rows}


def main():
    dry_run = "--dry-run" in sys.argv
    max_files = None
    if "--max" in sys.argv:
        max_files = int(sys.argv[sys.argv.index("--max") + 1])
    remote = list_remote_files()  # oldest first
    loaded = list_loaded_files()  # files already in staging
    missing = [n for n in remote if n not in loaded]
    print(f"remote {len(remote)}, in staging {len(loaded)}, missing {len(missing)}", file=sys.stderr)
    todo = missing[:max_files] if max_files else missing
    if len(todo) < len(missing):
        print(f"limited to {len(todo)} oldest of {len(missing)} missing", file=sys.stderr)
    os.makedirs(DATA_DIR, exist_ok=True)
    for name in todo:
        if dry_run:
            print(f"would download {name}", file=sys.stderr)
            continue
        target = os.path.join(DATA_DIR, name)
        if not os.path.exists(target):
            part = target + ".part"
            urllib.request.urlretrieve(BASE_URL + name, part)
            os.replace(part, target)
        print(target)


if __name__ == "__main__":
    main()
