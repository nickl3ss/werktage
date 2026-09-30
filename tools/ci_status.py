"""Wait for the CI run of a commit and list its jobs.

    GH_TOKEN=... python3 tools/ci_status.py <sha-prefix> [max_wait_seconds]

The token needs *Actions: read* on the repository. It is never printed.
"""
import json
import os
import sys
import time
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ.get("GH_REPO", "nickl3ss/werktags")
want, max_wait = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 480


def get(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode(), strict=False)


deadline = time.time() + max_wait
run = None
while time.time() < deadline:
    runs = get(f"repos/{REPO}/actions/runs?per_page=5").get("workflow_runs", [])
    run = next((r for r in runs if r["head_sha"].startswith(want)), None)
    state = f"{run['status']} {run['conclusion']}" if run else "no run yet"
    print(state, flush=True)
    if run and run["status"] == "completed":
        break
    time.sleep(30)
if run and run["status"] == "completed":
    for j in get(f"repos/{REPO}/actions/runs/{run['id']}/jobs")["jobs"]:
        bad = [s["name"] for s in j["steps"] if s["conclusion"] not in ("success", "skipped", None)]
        print(f"  {j['name']:10} {j['conclusion']:10} {bad if bad else ''}")
    print(run["html_url"])
