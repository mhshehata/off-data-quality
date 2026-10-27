"""Run the whole pipeline: fetch -> load -> transform -> rules.

Exit code 0: success, or nothing new to load.
Exit code non-zero: a stage failed (the stage name is on stderr).
The last stdout line is a JSON summary that n8n can read.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def run(stage, script, *args, capture=False):
    print(f"[{stage}] start", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        cwd=ROOT,
        stdout=subprocess.PIPE if capture else None,
        text=True,
    )
    if result.returncode != 0:
        print(f"[{stage}] FAILED with exit code {result.returncode}", file=sys.stderr)
        print(json.dumps({"status": "failed", "stage": stage}))
        sys.exit(result.returncode)
    return result.stdout.strip() if capture else ""


def main():
    fetch_args = [a for a in sys.argv[1:]]
    paths = run("fetch", "fetch_delta.py", *fetch_args, capture=True).splitlines()
    if not paths:
        print(json.dumps({"status": "nothing_new"}))
        return
    for path in paths:
        run("load", "load_raw.py", path)
        run("transform", "transform_staging.py", os.path.basename(path))
    run("rules", "run_dq_rules.py", *[os.path.basename(p) for p in paths])
    # Everything is in Postgres now (raw keeps every line), so the downloaded file is not needed.
    # Only reached when all stages succeeded; a failed run keeps its files for inspection.
    for path in paths:
        os.remove(path)
    print(json.dumps({"status": "ok", "source_files": [os.path.basename(p) for p in paths]}))


if __name__ == "__main__":
    main()