#!/usr/bin/env python3
"""
scripts/record_live_verification.py — a verification run writes the claim
(HOD-720).

The last mile of "deployment claims are derived, not remembered": after
.github/workflows/verify-live.yml has actually proven a capability against
the live deployment, THIS is what promotes it to `verified` in
docs/deployment_status.json — with the run that proved it and the moment it
did as the evidence.

Nothing else may promote a capability. A human editing the JSON to say
`verified` is exactly the drift the file exists to prevent, and
`deployment_status.py --check` will reject it if the evidence and date are
not there.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = ROOT / "docs" / "deployment_status.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a live verification result.")
    ap.add_argument("--verified", nargs="+", required=True,
                    help="capability names that passed live verification")
    ap.add_argument("--revision", default=None, help="the deployed revision that was verified")
    ap.add_argument("--evidence", default=None,
                    help="what proved it (defaults to the CI run URL, or a manual marker)")
    ap.add_argument("--at", default=None, help="RFC3339 timestamp (defaults to now)")
    args = ap.parse_args()

    doc = json.loads(STATUS_PATH.read_text())
    caps = doc["capabilities"]

    run_url = None
    server, repo, run_id = (os.environ.get("GITHUB_SERVER_URL"),
                            os.environ.get("GITHUB_REPOSITORY"),
                            os.environ.get("GITHUB_RUN_ID"))
    if server and repo and run_id:
        run_url = f"{server}/{repo}/actions/runs/{run_id}"
    evidence = args.evidence or run_url or "manual run of .github/workflows/verify-live.yml"
    stamp = args.at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    unknown = [name for name in args.verified if name not in caps]
    if unknown:
        print(f"Unknown capabilities: {unknown}. Add them to deployment_status.json first — "
              "this script records results, it does not invent capabilities.", file=sys.stderr)
        return 2

    for name in args.verified:
        cap = caps[name]
        previous = cap["status"]
        cap["status"] = "verified"
        cap["evidence_source"] = evidence
        cap["last_verified_utc"] = stamp
        if args.revision:
            cap["revision"] = args.revision
        print(f"  {name}: {previous} -> verified ({stamp})")

    STATUS_PATH.write_text(json.dumps(doc, indent=2) + "\n")

    # Refuse to leave the file in a state its own rules reject.
    sys.path.insert(0, str(ROOT))
    from scripts.deployment_status import load, validate
    failures = validate(load())
    if failures:
        print("Recorded status is invalid:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"\nRecorded {len(args.verified)} verified capabilities. "
          "Re-render the README table with `make deployment-status`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
