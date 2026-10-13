"""Load the rule catalogue from docs/sttm.xlsx into dq.dq_rule (rerun-safe)."""
import os

import openpyxl
import psycopg
from dotenv import load_dotenv

load_dotenv()

RULE_VERSION = 1

# STTM column 'If it fails' / 'Fix suggestion' are free text, so the mapping is explicit.
FIX_TYPE = {
    "R03": "lookup",
    "R04": "ai", "R05": "ai", "R06": "ai", "R07": "ai",
    "R08": "human",
    "R14": "human", "R15": "human", "R16": "human", "R17": "human",
    "R18": "human", "R19": "human", "R20": "human",
}

UPSERT = """
INSERT INTO dq.dq_rule
    (rule_id, rule_version, dimension, severity, check_description, fix_type, counts_against_score)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (rule_id, rule_version) DO UPDATE SET
    dimension = EXCLUDED.dimension,
    severity = EXCLUDED.severity,
    check_description = EXCLUDED.check_description,
    fix_type = EXCLUDED.fix_type,
    counts_against_score = EXCLUDED.counts_against_score
"""


def read_rules(path):
    ws = openpyxl.load_workbook(path, read_only=True)["STTM"]
    rules = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        rule_id, dimension, severity, check = row[6], row[7], row[8], row[5]
        if not rule_id or not str(rule_id).startswith("R"):
            continue  # field mapping without a rule
        short = str(rule_id).split("_")[0]
        rules.append((
            str(rule_id), RULE_VERSION, dimension, severity, check,
            FIX_TYPE.get(short, "none"),
            severity == "important",
        ))
    return rules


def main():
    rules = read_rules("docs/sttm.xlsx")
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"), port=int(os.environ.get("POSTGRES_PORT", "5433")), dbname="offdq", user="offdq",
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        for rule in rules:
            conn.execute(UPSERT, rule)
    print(f"loaded {len(rules)} rules")


if __name__ == "__main__":
    main()
