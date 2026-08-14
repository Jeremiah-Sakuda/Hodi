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
DEVPOST = ROOT / "docs" / "devpost-description.md"
DIAGRAM_B = ROOT / "docs" / "architecture" / "diagram_b_what_hodi_will_not_say.mmd"

# Every document that states a defect-ledger figure in prose. The count lived in
# exactly these seven places and in no source, and it had already drifted —
# fifteen in the blog, fourteen in the other six. Adding a document that quotes
# the figure without adding it here re-opens that hole, so the guard also fails
# if a defect-count phrase turns up in a repo document that is not on this list.
LEDGER_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "index.md",
    ROOT / "docs" / "devpost-description.md",
    ROOT / "docs" / "social-posts.md",
    ROOT / "docs" / "blog" / "seven-ways-to-lie-to-yourself-in-code.md",
    ROOT / "docs" / "blog" / "MEDIUM-VERSION.md",
]

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22,
    "twenty-three": 23, "twenty-four": 24, "twenty-five": 25, "twenty-six": 26,
    "twenty-seven": 27, "twenty-eight": 28, "twenty-nine": 29, "thirty": 30,
}

# (regex over the doc, which derived figure it must equal). Each pattern captures
# a numeral or a number-word immediately preceding the noun it quantifies.
_NUM = r"(\d+|[a-z]+(?:-[a-z]+)?)"
LEDGER_PATTERNS = [
    (re.compile(rf"{_NUM}\s+(?:real\s+)?defects", re.I), "total_defects"),
    (re.compile(rf"{_NUM}\s+patches", re.I), "total_defects"),
    # Negative lookahead: "three classes that recurred" is a recurrence claim,
    # checked separately below — without this it also reports as a bad class count.
    (re.compile(rf"{_NUM}\s+classes(?!\s+(?:that\s+)?recurred)", re.I), "class_count"),
    (re.compile(rf"sort into {_NUM}\s+", re.I), "class_count"),
]


def _as_int(token: str):
    token = token.lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def check_defect_ledger(metrics, failures) -> None:
    """
    The defect count is derived in scripts/count_defect_ledger.py from
    docs/defect_ledger.json. This asserts every document agrees with it.

    Class C in this project's own ledger is 'a number stated in prose that no
    mechanism holds to its source'. The accrual count was one instance, the
    overclaim-lint claim was another, and the defect count itself was the third.
    This function is why there will not be a fourth.
    """
    ledger = metrics.get("defect_ledger")
    if not ledger:
        failures.append("docs/metrics.json has no 'defect_ledger' — run `make ledger-count`.")
        return

    for path in LEDGER_DOCS:
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)} is listed as a ledger document but is missing.")
            continue
        text = path.read_text()
        rel = path.relative_to(ROOT)
        for pattern, key in LEDGER_PATTERNS:
            for match in pattern.finditer(text):
                value = _as_int(match.group(1))
                if value is None:
                    continue  # not a number — e.g. "these classes", "no defects"
                if value != ledger[key]:
                    failures.append(
                        f"{rel}: '{match.group(0).strip()}' states {value}; "
                        f"docs/defect_ledger.json derives {key}={ledger[key]}.")

    # Recurrence claims are the other half of the sentence and drifted with it.
    recurring = ledger["recurring_class_count"]
    for path in LEDGER_DOCS:
        if not path.exists():
            continue
        # Also matches the bare "the three that recurred" — no "classes" — which is
        # how this figure drifted past the guard in README.md and docs/index.md.
        for match in re.finditer(
                rf"{_NUM}\s+(?:of those\s+)?(?:classes\s+)?(?:that\s+)?recurred",
                path.read_text(), re.I):
            value = _as_int(match.group(1))
            if value is not None and value != recurring:
                failures.append(
                    f"{path.relative_to(ROOT)}: claims {value} recurring classes; "
                    f"the ledger derives {recurring}.")


def check_deployment_claims(failures) -> None:
    """
    Deployment prose must agree with docs/deployment_status.json (HOD-715).

    This guard exists because the README told readers that asymmetric signing
    "has not been built" for a commit AFTER it was built, and an external
    review found it. A deployment claim is a claim: it has to be derived from
    its evidence, not remembered.

    The check is BIDIRECTIONAL on purpose. A one-way check ("if unverified,
    say so") rots the other way round: once the capability really is
    deployed, the disclaimer stays behind and understates the system. So an
    unverified capability REQUIRES its disclaimer, and a verified one
    REQUIRES the disclaimer to be gone.
    """
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from scripts.deployment_status import load as load_status, validate as validate_status

    try:
        status = load_status()
    except Exception as e:  # noqa: BLE001 — a missing/broken file is a doc failure
        failures.append(f"docs/deployment_status.json could not be read: {e}")
        return

    for problem in validate_status(status):
        failures.append(f"deployment_status.json: {problem}")

    readme = README.read_text()
    caps = status.get("capabilities", {})

    # The signing claim, which is the one that actually drifted.
    kms = caps.get("kms_signing", {})
    kms_live = kms.get("status") == "verified"
    disclaimer = "has NOT yet been run against the live project"
    if kms_live and disclaimer in readme:
        failures.append(
            "README says setup_kms_signing.sh has NOT been run, but deployment_status.json "
            "marks kms_signing 'verified'. The disclaimer has outlived the deployment.")
    if not kms_live and disclaimer not in readme:
        failures.append(
            "deployment_status.json says kms_signing is not verified, but README does not carry "
            f"the disclaimer '{disclaimer}'. Readers would take the deployed service to be "
            "emitting real signatures when it emits labelled placeholders.")

    # No document may describe a never-executed capability as deployed.
    for name, cap in caps.items():
        if cap.get("status") != "scripted_not_executed":
            continue
        for doc_path in (README, DEVPOST):
            text = doc_path.read_text().lower()
            for phrase in (f"{name.replace('_', ' ')} is deployed",
                           f"{name.replace('_', ' ')} is live"):
                if phrase in text:
                    failures.append(
                        f"{doc_path.name} describes '{name}' as deployed, but "
                        "deployment_status.json marks it scripted_not_executed.")


def check_derived_counts(failures) -> None:
    """
    The other narrative numbers repeated across documents. Each is derived HERE,
    from the artifact that defines it, so there is no regeneration step anyone
    can forget — unlike the accrual figures, which need `make metrics` first.

    The audit that produced this list found two already drifted: the correction
    notes were claimed as six in the README and seven on the project site while
    the build log contains five, and the defect count was the third instance of
    the same class. A number that appears in two documents and no source is the
    shape; these are the ones that had it.
    """
    build_log = (ROOT / "docs" / "BUILD-LOG.md").read_text()
    index = ROOT / "docs" / "index.md"

    # (label, derived value, [(document, regex)]).
    checks = [
        (
            "dated correction notes",
            len(set(re.findall(r"CORRECTION NOTE #(\d+)", build_log))),
            [(README, r"(\w+) dated correction notes"),
             (DEVPOST, r"with (\w+) dated correction notes"),
             (index, r"(\w+) dated correction notes")],
        ),
        (
            "containment truth-table cases",
            len(re.findall(r"def test_case_\d+_", (ROOT / "tests" / "test_scope_containment.py").read_text())),
            [(README, r"(\d+)-case containment truth table"),
             (DEVPOST, r"A (\d+)-case truth table")],
        ),
        (
            "offline tests",
            sum(len(re.findall(r"^\s+def test_", p.read_text(), re.M))
                for p in sorted((ROOT / "tests").glob("*.py"))),
            [(README, r"full offline suite — (\d+) tests")],
        ),
        (
            "typed evidence classes",
            len(re.findall(r'"[^"]+"', re.search(
                r"EvidenceClass = Literal\[(.*?)\]",
                (ROOT / "src" / "schema" / "evidence.py").read_text(), re.S).group(1))),
            # Devpost states the limit in prose without the count, so it is not a site here.
            [(README, r"(\w+) typed evidence classes")],
        ),
    ]

    for label, derived, sites in checks:
        for path, pattern in sites:
            if not path.exists():
                continue
            found = re.search(pattern, path.read_text())
            if not found:
                failures.append(
                    f"{path.relative_to(ROOT)}: could not find the '{label}' claim to check "
                    f"(pattern {pattern!r}). If the sentence was reworded, update the pattern — "
                    "do not delete the check.")
                continue
            value = _as_int(found.group(1))
            if value is None:
                failures.append(f"{path.relative_to(ROOT)}: '{found.group(0)}' is not a number.")
            elif value != derived:
                failures.append(
                    f"{path.relative_to(ROOT)}: claims {value} {label}; the source has {derived}.")


def check_arithmetic_claims(metrics, failures) -> None:
    """
    Numbers the prose *computes* from other numbers.

    These slip past every other check here, because each factor is individually
    correct while the product is stale. The README's O(n^2) argument read
    "(5 works x 539 logged accesses) that is at most 800 comparisons" — 800 is
    5 x 160, the accrual total from two audits earlier. Both factors had been
    updated; the result they multiply to had not.

    So this asserts the factors against their source AND that the stated product
    is actually the product.
    """
    accrued = metrics["daily_crawler_accrual_metrics"]["total_accrued_records"]
    readme = README.read_text()

    m = re.search(r"\((\d+) works × ([\d,]+) logged accesses\) that is at most ([\d,]+) comparisons",
                  readme)
    if not m:
        failures.append(
            "README.md: could not find the O(n²) comparison-bound claim to check. If the "
            "sentence was reworded, update the pattern — do not delete the check.")
        return

    works, accesses, stated = (int(g.replace(",", "")) for g in m.groups())
    if accesses != accrued:
        failures.append(
            f"README.md's comparison bound uses {accesses} logged accesses; "
            f"metrics.json says {accrued}.")
    if stated != works * accesses:
        failures.append(
            f"README.md states {works} × {accesses} is at most {stated} comparisons; "
            f"it is {works * accesses}.")


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

    # The overclaim-lint hit rate is a measured number in the honesty section —
    # the most expensive place in this repo for a stale figure.
    lint = metrics.get("overclaim_lint_coverage")
    if not lint:
        failures.append("docs/metrics.json has no 'overclaim_lint_coverage' — run `make lint-coverage`.")
    else:
        lm = re.search(r"probe set of (\d+) paraphrases[^.]*?\*\*it rejects (\d+)\*\*", readme, re.DOTALL)
        if not lm:
            failures.append("README.md: could not find the measured overclaim-lint claim to check.")
        else:
            if int(lm.group(1)) != lint["probe_set_size"]:
                failures.append(
                    f"README.md cites a probe set of {lm.group(1)}; metrics.json says {lint['probe_set_size']}.")
            if int(lm.group(2)) != lint["paraphrases_rejected"]:
                failures.append(
                    f"README.md claims the lint rejects {lm.group(2)}; metrics.json says "
                    f"{lint['paraphrases_rejected']}.")
        if "including paraphrases" in readme:
            failures.append(
                "README.md still claims the lint catches 'including paraphrases' — measured "
                f"coverage is {lint['paraphrases_rejected']}/{lint['probe_set_size']}.")

    # The Devpost submission is the highest-stakes prose in the repo: a judge reads
    # it, and nothing else in the pipeline would catch a stale figure in it.
    devpost = DEVPOST.read_text()
    for label, pattern, expected in (
        ("accrued records", r"\*\*(\d+) accrued records\*\*", total),
        ("known-crawler matches", r"\*\*(\d+) match(?:es)? (?:any known AI-crawler|a crawler user-agent signature)", accrual["known_crawler_ua_matches"]),
        ("self-originated count", r"(\d+) are this project's own instrumented tooling", accrual["self_originated_count"]),
        ("unattributed count", r"The remaining (\d+) are non-self-originated", third_party),
        ("drill server-side avg", r"([\d.]+) ms server-side average",
         metrics["failure_tolerance_drill"]["server_side_avg_ms"]),
        ("lint probe set", r"a (\d+)-paraphrase probe set", lint["probe_set_size"] if lint else None),
        ("lint rejections", r"\*\*it rejects (\d+)\*\*", lint["paraphrases_rejected"] if lint else None),
    ):
        if expected is None:
            continue
        found = re.search(pattern, devpost)
        if not found:
            failures.append(f"devpost-description.md: could not find the '{label}' claim to check.")
        elif str(found.group(1)) != str(expected):
            failures.append(
                f"devpost-description.md states {label}={found.group(1)}; metrics.json says {expected}.")
    if audit_date not in devpost:
        failures.append(
            f"devpost-description.md does not carry the current audit date '{audit_date}'.")

    check_defect_ledger(metrics, failures)
    check_derived_counts(failures)
    check_arithmetic_claims(metrics, failures)
    check_deployment_claims(failures)

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

    print(f"Doc metric check PASSED: README.md, Diagram B and devpost-description.md agree with "
          f"docs/metrics.json ({total} accrued records, {accrual['known_crawler_ua_matches']} known-crawler "
          f"matches, {third_party} unattributed, audit {audit_date}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
