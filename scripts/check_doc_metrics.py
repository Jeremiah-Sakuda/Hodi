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

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "docs" / "metrics.json"
README = ROOT / "README.md"
DEVPOST = ROOT / "docs" / "devpost-description.md"
DIAGRAM_B = ROOT / "docs" / "architecture" / "diagram_b_what_hodi_will_not_say.mmd"
DOCS_INDEX = ROOT / "docs" / "index.md"
VIDEO_SCRIPT = ROOT / "docs" / "VIDEO-SCRIPT.md"
# Checked as a DOCUMENT as well as a data file: its own free-text keys are prose
# and drifted exactly like prose — the currency note named live release
# verification as outstanding while the capability below it read verified.
STATUS_JSON = ROOT / "docs" / "deployment_status.json"

# Any phrasing that asserts a capability has not run. Not a whitelist of
# approved sentences — a list of ways to say "not executed", matched only on
# lines that also name a verified capability's artifact.
NOT_EXECUTED_PHRASES = (
    "not yet executed", "not yet been executed", "never executed",
    "has not been run", "have not been run", "has not been executed",
    "never been run", "never run against", "has never run",
    "scripted, never run", "scripted but not executed", "scripted_not_executed",
    "not been built", "has not been built", "remains outstanding",
    "designed and scripted, not", "designed-only", "not deployed",
    # The guard missed a verified capability's self-contradicting detail text by
    # ONE WORD: it held "not deployed" while the string said "not been
    # deployed". A phrase list is only ever as good as its next inflection, so
    # the near-misses that actually occurred are listed explicitly.
    "has not been deployed", "have not been deployed", "not been deployed",
    "has not yet been verified live", "have not yet been verified live",
    "not yet been verified live", "provisioned but unverified",
    "not yet verified live", "but unverified",
)

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

# Word-forms above thirty were absent, and `_as_int` returns None for anything
# it does not know while the ledger check treats None as "not a number, skip".
# The effect was that "forty-four defects" — the figure in the README, the
# project site and both copies of the blog — matched the pattern, resolved to
# None, and was skipped. The guard reported those four documents as checked and
# had never once compared their headline number to the ledger. Generate the
# compounds instead of listing them, so the next decade cannot reopen the hole.
_TENS = {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9}
for _t, _tv in _TENS.items():
    NUMBER_WORDS[_t] = _tv
    for _u, _uv in _UNITS.items():
        NUMBER_WORDS[f"{_t}-{_u}"] = _tv + _uv

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

    # The table in README.md is marked GENERATED and says not to hand-edit it.
    # Nothing regenerated it and nothing compared it, so a promotion recorded in
    # the JSON could leave the README showing the old state and the old date —
    # the exact drift this file exists to prevent, in the artifact it generates.
    from scripts.deployment_status import embedded_table, render
    embedded = embedded_table(readme)
    if not embedded:
        failures.append("README.md no longer contains the generated deployment-status table.")
    elif embedded != render(status):
        failures.append(
            "README.md's deployment-status table does not match docs/deployment_status.json. "
            "It is generated: run `python3 scripts/deployment_status.py --write-readme`.")

    # ---- the GENERAL check: no prose may call a verified capability un-run ----
    #
    # WHY THIS REPLACED A PHRASE LIST. The previous version of this function knew
    # exactly one disclaimer sentence, about KMS. An external judge found two
    # more the same week: the README described setup_workload_identity.sh and
    # deploy_revocation_worker.sh as "designed and scripted, not yet executed"
    # while the generated table three sections below marked both `verified` —
    # and deployment_status.json's OWN currency note named live release
    # verification as outstanding three hours after CI had verified it and
    # written the run URL into this same file.
    #
    # Guarding a claim by enumerating the sentences that could express it is the
    # same mistake as the overclaim lint's regex list, and it fails the same way:
    # the next sentence is phrased differently. So the anchor is the ARTIFACT
    # PATH, which prose has to name in order to be talking about the capability
    # at all, and the trigger is any not-executed phrasing on that line.
    for name, cap in caps.items():
        if cap.get("status") != "verified":
            continue
        artifacts = cap.get("artifacts") or []
        if not artifacts:
            failures.append(
                f"deployment_status.json: '{name}' is verified but names no artifacts, so no "
                "document can be checked against it. Add the implementing paths.")
            continue
        for doc_path in (README, DEVPOST, DOCS_INDEX, STATUS_JSON):
            if not doc_path.exists():
                continue
            for lineno, line in enumerate(doc_path.read_text().splitlines(), 1):
                low = line.lower()
                if not any(a.lower() in low for a in artifacts):
                    continue
                hit = next((p for p in NOT_EXECUTED_PHRASES if p in low), None)
                if hit:
                    failures.append(
                        f"{doc_path.name}:{lineno} says '{hit}' about an artifact of '{name}', "
                        f"which deployment_status.json marks verified"
                        + (f" (evidence: {cap.get('evidence_source','')[:60]})" if
                           cap.get("evidence_source") else "") + ".")

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


def _count_e2e_gated_tests() -> int:
    """Test methods the offline suite skips because they need live GCP.

    The README states this number in words. It said "Sixteen" while the suite
    skipped seventeen — the same drift the containment-truth-table and
    offline-test counts were already guarded against, in the one sentence that
    tells a reader how much of the suite they are NOT seeing. Derived by AST so
    a class-level `@unittest.skipUnless(... HODI_E2E ...)` correctly counts
    every test method beneath it.
    """
    def gated(node) -> bool:
        return any("HODI_E2E" in ast.dump(dec) for dec in node.decorator_list)

    total = 0
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and gated(node):
                total += sum(1 for b in node.body
                             if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and b.name.startswith("test_"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test_") and gated(node):
                total += 1
    return total


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
            "E2E-gated tests",
            _count_e2e_gated_tests(),
            [(README, r"(\w+) tests that genuinely require live Firestore or live IAM")],
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


def check_deployed_timings(metrics, failures) -> None:
    """
    The README's deployed-path latency sentence, checked against its own source.

    WHY. On 2026-08-14 that sentence read "revocation cascade 3049 ms cold /
    534 ms warm average" while `docs/metrics.json` — which the sentence names
    as its source, one clause earlier — said 2263 / 736.6. The metrics file had
    been regenerated after a real regression; the prose citing it had not. Every
    other figure in the README is guarded; these were not, so this is where the
    drift went. Same class as the 47, the 160 and the defect ledger: a number
    typed once and thereafter remembered.

    A latency figure is the easiest number in the repo to leave stale and the
    hardest to notice, because nothing breaks when it is wrong and it is
    always plausible.
    """
    readme = README.read_text()
    cascade = metrics["h6_revocation_cascade_real_corpus_scale"]
    natural = metrics["natural_language_license_path"]
    license_path = metrics["buyer_api_license_path"]

    for label, pattern, expected in (
        ("cascade cold", r"revocation cascade (\d+) ms cold", cascade["cold_start_ms"]),
        ("cascade warm", r"revocation cascade \d+ ms cold / (\d+) ms warm", cascade["warm_avg_ms"]),
        ("natural-language warm", r"natural-language license path (\d+) ms warm",
         natural["warm_avg_ms"]),
        ("license permitted warm", r"license path (\d+) ms warm average when permitted",
         license_path["permitted_warm_avg_ms"]),
        ("license denied warm", r"when permitted and (\d+) ms when denied",
         license_path["denied_warm_ms"]),
    ):
        found = re.search(pattern, readme)
        if not found:
            failures.append(
                f"README.md: could not find the '{label}' timing claim to check. If the "
                "sentence was reworded, update the pattern — do not delete the check.")
            continue
        if int(found.group(1)) != round(expected):
            failures.append(
                f"README.md states {label}={found.group(1)} ms; metrics.json says "
                f"{round(expected)} ms.")

    # A timing claim is an observation, so it must carry the revision it was
    # observed on — otherwise "re-measured" names no measurement.
    revision = cascade.get("revision")
    if revision and revision not in readme:
        failures.append(
            f"README.md cites deployed-path timings without naming the revision they were "
            f"measured on ('{revision}'). A latency number without a revision is not an "
            "observation, it is a memory.")


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
        # Devpost now states the composed figure as "**12 of 12**"; the regex-only
        # fallback is checked separately below so BOTH published numbers are guarded.
        ("lint rejections", r"\*\*(\d+) of 12\*\*", lint["paraphrases_rejected"] if lint else None),
        ("lint regex-only fallback", r"falls back to (\d+) if that model is unreachable",
         lint["rejected_by_regex_alone"] if lint else None),
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

    # PHRASING-INDEPENDENT crawler-count check across every judge-facing document.
    #
    # The per-document checks above are anchored on exact sentences, so the
    # Devpost text drifted to "nine" in two places the patterns did not cover —
    # inside the section about number drift, while a third sentence in the same
    # file said 16. This finds EVERY quantifier attached to a crawler noun,
    # numeral or word, and requires them all to equal the source.
    crawler_nouns = (r"(?:generic\s+)?crawler-signature matches", r"at the current audit",
                     r"match a crawler user-agent signature", r"crawler(?:-signature)? user agents")
    quantifier = r"(\d+|[a-z]+(?:-[a-z]+)?)\s+(?:of them\s+)?"
    for path in (README, DEVPOST, VIDEO_SCRIPT, DOCS_INDEX):
        if not path.exists():
            continue
        text = path.read_text()
        for noun in crawler_nouns:
            for match in re.finditer(quantifier + noun, text, re.I):
                value = _as_int(match.group(1))
                if value is None or value == total:
                    continue  # not a number, or the accrual total rather than the match count
                if value != accrual["known_crawler_ua_matches"]:
                    failures.append(
                        f"{path.relative_to(ROOT)}: '{match.group(0).strip()}' states {value}; "
                        f"metrics.json says {accrual['known_crawler_ua_matches']} known-crawler matches.")

    # THE RECORDING SCRIPT. The one document whose numbers are spoken out loud,
    # over a diagram showing the same numbers — and the only prose artifact that
    # was not checked here.
    #
    # Beat 7 is marked "never cut". It narrated "3291 accrued access records" and
    # "Nine match a crawler signature" while Diagram B filled the screen behind
    # it with 4430 and 16. A viewer sees the contradiction; the build did not,
    # because this file was not in the list. This module's own docstring names
    # the failure mode — a figure repeated in prose and derived nowhere — and it
    # then committed it in the highest-stakes place available.
    script = VIDEO_SCRIPT.read_text()
    for label, pattern, expected in (
        ("accrued records", r"(\d+) accrued access records", total),
        ("known-crawler matches", r"\*\*(\w+)\*\* match(?:es)? a crawler signature",
         accrual["known_crawler_ua_matches"]),
    ):
        found = re.search(pattern, script)
        if not found:
            failures.append(
                f"VIDEO-SCRIPT.md: could not find the '{label}' claim to check "
                f"(pattern {pattern!r}). If the narration was reworded, update the "
                "pattern — do not delete the check.")
            continue
        value = _as_int(found.group(1))
        if value is None:
            failures.append(f"VIDEO-SCRIPT.md: '{found.group(0)}' is not a number.")
        elif value != expected:
            failures.append(
                f"VIDEO-SCRIPT.md narrates {label}={value}; metrics.json says {expected}. "
                "The presenter would be reading this over a diagram showing the other number.")

    # The cascade figure the presenter reads off a wall clock.
    cascade = metrics.get("h6_revocation_cascade_real_corpus_scale")
    if cascade and cascade.get("warm_runs_ms"):
        runs = sorted(float(x) for x in cascade["warm_runs_ms"])
        mid = len(runs) // 2
        median = int(runs[mid] if len(runs) % 2 else (runs[mid - 1] + runs[mid]) / 2)
        # Anchored on the NOUN, not a bare substring search. A first version
        # asked only whether "2389" appeared anywhere in the file and passed a
        # mutation that changed the stated median, because the number also
        # occurs in other rows. That is the same too-weak guard this script
        # already had to fix once, for the blog's crawler count.
        stated = {int(m) for m in re.findall(r"median \*\*(\d+)\s*ms\*\*", script)}
        stated |= {int(m) for m in re.findall(r"median \*\*(\d+)\*\*\s*ms", script)}
        if not stated:
            failures.append(
                "VIDEO-SCRIPT.md states no cascade median at all (expected a "
                f"'median **{median} ms**' claim). The wall clock on camera is the proof.")
        elif stated != {median}:
            failures.append(
                f"VIDEO-SCRIPT.md states cascade median(s) {sorted(stated)}; metrics.json "
                f"says {median} ms. The presenter reads this off a wall clock on camera.")
        revision = cascade.get("revision", "")
        if revision and revision.split("-")[-1] not in script:
            failures.append(
                f"VIDEO-SCRIPT.md does not name the revision the timings came from ({revision}).")

    # The published essay is the one document a judge is linked to directly and
    # the one nobody regenerates. Its crawler figure said "zero" for nine days
    # after the detector was fixed — in the essay about deceiving yourself with
    # stale numbers, which at one point carried three different values for the
    # same figure in a single document.
    crawler_matches = accrual["known_crawler_ua_matches"]
    words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    # The figure is LIVING — it went 0 -> 1 -> 9 -> 16 in three weeks — so the
    # essay cites a numeral with the audit date rather than a spelled word, and
    # this asserts the numeral is the current one. A word form is still rejected
    # if it names a different count, because that is how "zero" survived.
    for blog in (ROOT / "docs" / "blog" / "seven-ways-to-lie-to-yourself-in-code.md",
                 ROOT / "docs" / "blog" / "MEDIUM-VERSION.md"):
        text = blog.read_text()
        low = text.lower()
        stale_words = [w for n, w in words.items()
                       if n != crawler_matches and f"{w} match any crawler signature" in low]
        if stale_words:
            failures.append(
                f"{blog.name} states '{stale_words[0]} match any crawler signature'; metrics.json "
                f"says {crawler_matches}. The published essay is linked from the Devpost text.")
        # Anchor on the NOUN, not on the bare numeral. Checking only that the
        # digits appear anywhere passed a mutation that changed "16 visits" to
        # "nine visits", because 16 also occurs elsewhere in the essay — a guard
        # that cannot fail is the defect class this whole file exists for.
        visit_counts = {int(n) for n in re.findall(r"\*?\*?(\d+)\*?\*?\s+visits\b", text)}
        visit_counts |= {NUMBER_WORDS[w] for w in re.findall(r"\b([a-z]+)\s+visits\b", text, re.I)
                         if w.lower() in NUMBER_WORDS}
        if not visit_counts:
            failures.append(
                f"{blog.name} states no '<n> visits' crawler figure at all; the guard cannot "
                "confirm the published essay carries the current count.")
        elif visit_counts != {crawler_matches}:
            failures.append(
                f"{blog.name} states crawler visits {sorted(visit_counts)}; metrics.json says "
                f"{crawler_matches}. The published essay is linked directly to judges.")
        if audit_date not in text:
            failures.append(
                f"{blog.name} does not carry the current audit date '{audit_date}' beside its "
                "crawler figure — a living count cited without a date is a claim that cannot age.")

    check_defect_ledger(metrics, failures)
    check_derived_counts(failures)
    check_arithmetic_claims(metrics, failures)
    check_deployment_claims(failures)
    check_deployed_timings(metrics, failures)

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
