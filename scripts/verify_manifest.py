#!/usr/bin/env python3
"""
scripts/verify_manifest.py — `make verify-manifest` (HOD-009, HOD-105).

Fetches the LIVE /works manifest from the deployed evidence endpoint (public,
no credentials) and verifies the corpus-integrity properties:

  1. The manifest serves the registered corpus (exactly 5 works).
  2. Every work is one of the three control tiers, and no work at
     'verified_control' lacks a stored control_proof.
  3. Every verified_control proof URI resolves with HTTP 200 — a proof that
     does not resolve is treated as no proof at all.
  4. Every work carries a canary string with its plant date.

Exits nonzero on any violation. Numbers printed here are read from the live
manifest, never typed.
"""

import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
VALID_TIERS = {"verified_control", "asserted", "disputed"}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Hodi-HealthCheck/1.0"})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_200(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hodi-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    print(f"Fetching live manifest: {BASE_URL}/works")
    manifest = fetch_json(f"{BASE_URL}/works")
    works = manifest.get("works", [])
    print(f"Manifest reports {manifest.get('count')} works; body contains {len(works)}.")

    failures = []

    if len(works) != 5:
        failures.append(f"Expected the 5-work registered corpus, found {len(works)}.")

    tier_counts = {}
    for w in works:
        wid = w.get("work_id", "<missing work_id>")
        tier = w.get("control_tier")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        if tier not in VALID_TIERS:
            failures.append(f"{wid}: invalid control_tier '{tier}'.")

        if tier == "verified_control":
            proof = w.get("control_proof")
            if not proof:
                failures.append(f"{wid}: verified_control WITHOUT stored control_proof (HOD-105 violation).")
            else:
                uri = proof.get("evidence_uri", "")
                if uri.startswith("http"):
                    if check_200(uri):
                        print(f"  [200 OK] {wid} proof: {uri}")
                    else:
                        failures.append(f"{wid}: verified_control proof URI does not resolve: {uri}")
                else:
                    failures.append(f"{wid}: verified_control proof URI is not verifiable over HTTP: {uri}")
        elif proof_is_present := bool(w.get("control_proof")):
            print(f"  [note] {wid} is '{tier}' and also stores a proof object.")

        if not w.get("canary_string") or not w.get("canary_planted_at"):
            failures.append(f"{wid}: missing canary_string or canary_planted_at.")

    print(f"Control-tier distribution (live): {json.dumps(tier_counts)}")

    if failures:
        print("\nMANIFEST VERIFICATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("\nMANIFEST VERIFICATION PASSED: corpus served live, tiers valid, every "
          "verified_control proof resolves, canaries present.")


if __name__ == "__main__":
    main()
