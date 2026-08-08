#!/usr/bin/env python3
"""
scripts/check_doc_metrics.py — enforces the Literal Metric Rendering Rule on the
docs themselves (`make check-docs`).

Every accrual number written into README.md or Diagram B must equal what
`docs/metrics.json` currently says. Prose numbers are a snapshot the moment they
are typed; without this check they drift silently, and the first thing a
skeptical reader does is run `make metrics` and compare.

That is exactly what happened: the README claimed "160 accrued records, zero
attributable to third parties" while `make metrics` produced 248 records and a
non-zero third-party count — the project's signature honesty finding refuted by
the project's own documented command. See BUILD-LOG correction #7.

Exits nonzero listing every mismatch, so the fix is always "regenerate, then
update the docs", never "hope nobody checks".
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "docs" / "metrics.json"
README = ROOT / "README.md"
DIAGRAM_B = ROOT / "docs" / "architecture" / "diagram_b_what_hodi_will_not_say.mmd"


def main() -> int:
    metrics = json.loads(METRICS.read_text())
    accrual = metrics["daily_crawler_accrual_metrics"]
    total = accrual["total_accrued_records"]
    third_party = accrual["non_self_originated_requests_count"]
    audit_date = accrual["audit_date_utc"]

    failures = []

    readme = README.read_text()
    # "As of the <date> audit ...: N accrued records"
    m = re.search(r"(\d+)\s+accrued records", readme)
    if not m:
        failures.append("README.md: could not find an 'N accrued records' claim to check.")
    elif int(m.group(1)) != total:
        failures.append(
            f"README.md claims {m.group(1)} accrued records; metrics.json says {total}."
        )

    if audit_date not in readme:
        failures.append(
            f"README.md does not carry the current audit date '{audit_date}' — an accrual "
            "claim must be dated, because it is an observation, not a standing fact."
        )

    # The third-party claim is phrased in words when zero; check it matches reality.
    claims_zero = "zero attributable to third parties" in readme
    if claims_zero and third_party != 0:
        failures.append(
            f"README.md claims zero third-party accrual; metrics.json says {third_party}."
        )
    if not claims_zero and third_party == 0:
        failures.append(
            "metrics.json shows zero third-party accrual but README.md no longer states it."
        )

    diagram = DIAGRAM_B.read_text()
    dm = re.search(r"(\d+)\s+records accrued", diagram)
    if not dm:
        failures.append("Diagram B: could not find an 'N records accrued' label to check.")
    elif int(dm.group(1)) != total:
        failures.append(
            f"Diagram B labels {dm.group(1)} records accrued; metrics.json says {total}."
        )
    if audit_date not in diagram:
        failures.append(f"Diagram B does not carry the current audit date '{audit_date}'.")

    if failures:
        print("DOC METRIC CHECK FAILED — docs disagree with docs/metrics.json:")
        for f in failures:
            print(f"  - {f}")
        print("\nFix: run `make metrics`, then update README.md and Diagram B "
              "(and re-render the PNG) to the regenerated numbers.")
        return 1

    print(f"Doc metric check PASSED: README.md and Diagram B agree with docs/metrics.json "
          f"({total} accrued records, {third_party} third-party, audit {audit_date}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
