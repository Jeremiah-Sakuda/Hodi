"""
tests/test_submission_exposure.py — the repository must not publish an
evaluation score, and must not name a real company as a violator (HOD-740).

TWO RULES THIS PROJECT WROTE DOWN AND THEN BROKE.

1. `docs/BUILD-LOG.md` states, in bold, that no outside body has evaluated this
   project — and records that evaluation framing was deliberately removed from
   five separate passages. One survived: a session summary opened with a
   score literal and a stage verdict. A scrub performed by reading is a scrub
   that misses one, every time; this is the mechanism that reading lacked.

2. `AGENTS.md` and `docs/PRD.md` both state: *no real company appears as a
   violator in the repo, the video, the blog, or any social post* — and
   `docs/devpost-description.md` repeats the promise to judges. Five prose
   passages named a specific vendor's crawler as the observed crawler.

WHERE THE LINE IS, AND WHY IT IS NOT "NEVER SAY THE STRING". Observed data is
evidence and is not edited: `docs/metrics.json` is GENERATED from the live
Firestore audit, and rewriting a recorded user agent to satisfy a prose rule
would be tampering with the record — the opposite of what the rule protects.
The rule governs PROSE, which is where a claim about a party is made. So the
generated metrics file is exempt by name, its own `claim_limit` states the
policy, and every hand-written document must anonymize.
"""

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Generated evidence. Exempt from the prose rule, and only these.
GENERATED_EVIDENCE = {
    "docs/metrics.json",
    "fixtures/gemini_response_cache.json",
    "fixtures/embedding_cache.json",
}

# Fixtures are deliberately fictional adversaries; the rule is about REAL
# parties, and a test asserting the fictional ones exist lives elsewhere.
FIXTURE_PREFIXES = ("fixtures/", "tests/")

# Real crawler vendors that must not be named in prose as the observed crawler.
# Generic self-identification (`bot`, `crawler`, `spider`) is what the detector
# matches and what the docs may say.
VENDOR_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "CCBot", "Bytespider",
                   "Googlebot", "Amazonbot", "PerplexityBot", "Applebot")

SCORE_PATTERNS = (
    re.compile(r"\b\d\.\d+\s*/\s*6\b"),          # a weighted score out of six
    re.compile(r"\bStage One\s+(PASS|FAIL)\b", re.I),
    re.compile(r"\bStage Two\s+(score|total)\b", re.I),
)


def tracked_text_files():
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT).decode().split("\n")
    for rel in out:
        if not rel or rel in GENERATED_EVIDENCE:
            continue
        if not rel.endswith((".md", ".py", ".sh", ".json", ".yml", ".yaml", ".js", ".mmd")):
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        yield rel, p.read_text(errors="replace")


class NoEvaluationScoreIsPublishedTest(unittest.TestCase):
    """A score in the repository reads as a leaked evaluation result."""

    def test_no_score_literal_or_stage_verdict_in_any_tracked_file(self):
        offenders = []
        for rel, text in tracked_text_files():
            if rel == "tests/test_submission_exposure.py":
                continue  # this file names the patterns it forbids
            for lineno, line in enumerate(text.splitlines(), 1):
                for pat in SCORE_PATTERNS:
                    if pat.search(line):
                        offenders.append(f"{rel}:{lineno}: {line.strip()[:110]}")
        self.assertFalse(
            offenders,
            "an evaluation score or stage verdict is published in the repository:\n  "
            + "\n  ".join(offenders))

    def test_the_build_log_still_states_no_outside_evaluation(self):
        """
        The claim this guard protects. If the sentence is ever removed, the
        guard is protecting nothing and should be revisited deliberately.
        """
        text = (ROOT / "docs" / "BUILD-LOG.md").read_text(errors="replace")
        self.assertIn("No outside body has evaluated this project", text)


class NoRealCompanyIsNamedAsAViolatorTest(unittest.TestCase):
    """The rule AGENTS.md, the PRD and the Devpost text all promise."""

    def test_no_vendor_crawler_is_named_in_prose(self):
        offenders = []
        for rel, text in tracked_text_files():
            if rel == "tests/test_submission_exposure.py":
                continue
            if rel.startswith(FIXTURE_PREFIXES):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for vendor in VENDOR_CRAWLERS:
                    if vendor.lower() in line.lower():
                        offenders.append(f"{rel}:{lineno} names '{vendor}': {line.strip()[:90]}")
        self.assertFalse(
            offenders,
            "a real company is named as the observed crawler, which AGENTS.md, docs/PRD.md and "
            "docs/devpost-description.md all promise does not happen:\n  " + "\n  ".join(offenders))

    def test_the_generated_metrics_file_states_its_own_exemption(self):
        """
        The exemption has to be visible where the strings are, or it looks like
        the rule was simply broken there too.
        """
        m = json.loads((ROOT / "docs" / "metrics.json").read_text())
        limit = m["daily_crawler_accrual_metrics"]["claim_limit"]
        self.assertIn("user agent", limit.lower())
        self.assertIn("not an accusation", limit.lower(),
                      "metrics.json publishes observed vendor user agents; its claim_limit must say "
                      "plainly that a recorded user agent is evidence of a request, not an "
                      "accusation against the party it names")


if __name__ == "__main__":
    unittest.main()
