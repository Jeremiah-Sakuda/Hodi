#!/usr/bin/env python3
"""
scripts/measure_lint_coverage.py — measures what the overclaim lint ACTUALLY
catches, and writes the figure into docs/metrics.json (`make lint-coverage`).

The README claimed the lint rejects overclaims "including paraphrases". It does
not, and an overstatement in the honesty section is the most expensive place in
this repo to have one.

The probe set below is deliberately seeded from paraphrases the lint was NOT
written against — per AGENTS.md, "the lints are adversarial: seed the overclaim
lint from paraphrases it was not written against, not from its own token list."
Any probe that merely restates a pattern in FORBIDDEN_PHRASES would inflate the
score into meaninglessness.

The measured rate is written to metrics.json so the README can cite a number
that regenerates, rather than one that was typed once and then drifted.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evidence.overclaim_lint import OverclaimLint, OverclaimLintViolation

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "docs" / "metrics.json"

# Paraphrases asserting training-set membership, none of which reuses the
# lint's own token list verbatim.
PARAPHRASE_PROBES = [
    "This proves the model saw your work.",
    "Your essay is inside the model's weights.",
    "We can confirm your work was used to build this model.",
    "The model has clearly memorized your lyrics.",
    "This is evidence your art became part of the dataset.",
    "Your recordings were absorbed during pretraining.",
    "The system learned from your copyrighted material.",
    "This demonstrates ingestion of your work into the corpus.",
    "Your work was scraped and fed to the model.",
    "The weights contain your writing.",
    "This model was trained on your images.",
    "Your content was in the training set.",
]


def measure():
    lint = OverclaimLint()
    caught, missed = [], []
    for probe in PARAPHRASE_PROBES:
        try:
            lint.lint_text(probe)
            missed.append(probe)
        except OverclaimLintViolation:
            caught.append(probe)
    return caught, missed


def main() -> int:
    caught, missed = measure()
    total = len(PARAPHRASE_PROBES)

    print(f"Overclaim lint paraphrase coverage: {len(caught)}/{total} rejected")
    print("\nNOT rejected (the lint would let these through):")
    for m in missed:
        print(f"  - {m}")

    metrics = json.loads(METRICS.read_text())
    # Record the REGEX-ONLY figure alongside the composed one. The backstop is a
    # model, and a model can regress or become unreachable; publishing only the
    # combined number would hide how much of the coverage depends on it.
    import re as _re
    regex_only = [p for p in PARAPHRASE_PROBES
                  if any(_re.search(pat, (p if isinstance(p, str) else p[0]).lower())
                         for pat in OverclaimLint.FORBIDDEN_PHRASES)]

    metrics["overclaim_lint_coverage"] = {
        "measured_at_utc": metrics.get("timestamp"),
        "probe_set_size": total,
        "paraphrases_rejected": len(caught),
        "paraphrases_not_rejected": len(missed),
        "rejected_by_regex_alone": len(regex_only),
        "rejected_by_semantic_backstop": len(caught) - len(regex_only),
        "layers": ("deterministic regex list, then an embedding backstop "
                   "(src/evidence/semantic_backstop.py, gemini-embedding-001) that can only ADD "
                   "refusals; with the backstop unreachable, coverage falls back to "
                   "rejected_by_regex_alone"),
        "probe_set_source": "scripts/measure_lint_coverage.py::PARAPHRASE_PROBES",
        "claim_limit": (
            "The lint is a backstop against the exact phrasings it enumerates, not a "
            "general paraphrase detector. The STRUCTURAL guarantee is the schema: "
            "EvidenceRecord.class has no training-membership value, so the system cannot "
            "emit the claim as data. The lint only reduces the chance of it appearing in "
            "free text."
        ),
    }
    METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"\nWrote 'overclaim_lint_coverage' to {METRICS}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
