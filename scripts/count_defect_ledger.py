#!/usr/bin/env python3
"""
scripts/count_defect_ledger.py — derive the defect-ledger figures from the
ledger rather than from anyone's memory (HOD-620).

    make ledger-count

Reads docs/defect_ledger.json, counts, and writes `defect_ledger` into
docs/metrics.json. scripts/check_doc_metrics.py then fails the build if any
document's stated figure disagrees.

WHY. The defect count was typed into seven documents by hand and drifted:
fifteen in the blog after the ISO-sort defect was added, fourteen in the README
(twice), docs/index.md, the Devpost description, the Medium copy and social post
one. That is the same shape as the accrual-count drift (correction #7) and the
overclaim-lint claim: a number repeated in prose with no mechanism holding it to
a source. Generation-from-source is this project's answer to that shape, so the
number is now generated from a source.

Run with --check to verify metrics.json is current without rewriting it.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "defect_ledger.json"
METRICS = ROOT / "docs" / "metrics.json"


def derive() -> dict:
    ledger = json.loads(LEDGER.read_text())
    classes = ledger["classes"]

    ids = [d["id"] for c in classes for d in c["defects"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise SystemExit(f"defect_ledger.json has duplicate defect ids: {duplicates}")

    missing_source = [d["id"] for c in classes for d in c["defects"] if not d.get("source")]
    if missing_source:
        raise SystemExit(
            "every ledger entry must name a primary source in this repository; "
            f"these do not: {missing_source}")

    return {
        "source": "docs/defect_ledger.json",
        "counting_rule": ledger["counting_rule"],
        "total_defects": len(ids),
        "class_count": len(classes),
        "recurring_class_count": sum(1 for c in classes if c["recurred"]),
        "defects_per_class": {c["id"]: len(c["defects"]) for c in classes},
        "recurring_classes": [c["id"] for c in classes if c["recurred"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-metrics", action="store_true",
                    help="write the derived figures into docs/metrics.json")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if metrics.json is stale (no write)")
    args = ap.parse_args()

    derived = derive()
    metrics = json.loads(METRICS.read_text())
    current = metrics.get("defect_ledger")

    print(f"Derived from {LEDGER.relative_to(ROOT)}:")
    print(f"  total defects        : {derived['total_defects']}")
    print(f"  classes              : {derived['class_count']}")
    print(f"  classes that recurred: {derived['recurring_class_count']} "
          f"({', '.join(derived['recurring_classes'])})")
    for cid, n in derived["defects_per_class"].items():
        print(f"      {cid:38} {n}")

    if args.check:
        if current != derived:
            print("\nSTALE: docs/metrics.json disagrees with the ledger. "
                  "Run `make ledger-count`.", file=sys.stderr)
            return 1
        print("\ndocs/metrics.json is current.")
        return 0

    if args.write_metrics:
        metrics["defect_ledger"] = derived
        METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
        print(f"\nWrote 'defect_ledger' to {METRICS.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
