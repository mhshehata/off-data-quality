"""HTTP wrapper around run_pipeline.py so n8n can trigger it."""
import json
import os
import subprocess
import sys
import threading

from flask import Flask

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "scripts", "run_pipeline.py")

app = Flask(__name__)
lock = threading.Lock()


@app.route("/run", methods=["POST"])
def run():
    if not lock.acquire(blocking=False):
        return {"status": "busy"}, 409
    try:
        result = subprocess.run(
            [sys.executable, PIPELINE], cwd=ROOT, capture_output=True, text=True
        )
    finally:
        lock.release()

    print(result.stderr, file=sys.stderr)
    try:
        body = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        body = {"status": "failed", "stage": "unknown"}
    return body, (200 if result.returncode == 0 else 500)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
