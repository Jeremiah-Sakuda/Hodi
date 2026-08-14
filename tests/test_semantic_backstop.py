"""
tests/test_semantic_backstop.py — the embedding backstop may only ever tighten
the overclaim lint (HOD-320, HOD-350).

Hodi's standing rule is that a model never decides anything. This is the one
model in the codebase that participates in a refusal, so the property that makes
it admissible has to be asserted, not asserted-about:

    lint(text) = regex_reject(text) OR semantic_reject(text)

is MONOTONIC IN STRICTNESS. There is no input for which enabling the backstop
permits text the regexes would have rejected — so a wrong embedding produces a
false REFUSAL (Hodi emits the linted deterministic template instead of a drafted
notice), never a false permission. That direction of failure is the whole
argument for allowing a model here at all.

The second property is negation survival. Every drafted revocation notice is
REQUIRED to contain "does not un-train" (src/llm/notice_drafter.py), and that
sentence denies the forbidden claim while sitting close to it in embedding
space. A one-sided similarity cut rejected it — observed, not hypothesised —
which would have made the backstop refuse the exact text the system exists to
produce. Nearest-anchor classification against PERMITTED_CLAIM_ANCHORS is the
fix, and `test_negated_claims_are_not_refused` is what keeps it fixed.
"""

import os
import re
import unittest

from src.evidence.overclaim_lint import OverclaimLint, OverclaimLintViolation
from src.evidence.semantic_backstop import (
    FORBIDDEN_CLAIM_ANCHORS, PERMITTED_CLAIM_ANCHORS, SIMILARITY_THRESHOLD,
    SemanticBackstop,
)
from src.llm.notice_drafter import TEMPLATE_NOTICE_TEXT

# Paraphrases that evade every regex but assert the forbidden claim.
EVASIVE_OVERCLAIMS = [
    "We can confirm your work was used to build this model.",
    "The model has clearly memorized your lyrics.",
    "This is evidence your art became part of the dataset.",
    "Your recordings were absorbed during pretraining.",
    "The system learned from your copyrighted material.",
    "Your work was scraped and fed to the model.",
]

# Text Hodi legitimately emits, including the negated phrasing notices require.
LEGITIMATE_TEXT = [
    TEMPLATE_NOTICE_TEXT,
    "This grant is hereby terminated. This revocation does not un-train the model.",
    "This record does not assert training-set membership.",
    "Crawler access observed at the evidence endpoint.",
    "A 14-token contiguous run of registered passage appears in the observed output. "
    "Co-occurrence of text only.",
    "The requested scope is not permitted by any active grant for this work.",
    "Training-set membership is not determinable and Hodi does not claim it.",
]


def regex_rejects(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in OverclaimLint.FORBIDDEN_PHRASES)


class BackstopIsStrictnessOnlyTest(unittest.TestCase):
    """The admissibility property: it can add refusals, never grants."""

    def setUp(self):
        self.backstop = SemanticBackstop()

    def test_backstop_never_permits_what_the_regexes_reject(self):
        """
        The monotonicity assertion. For every text the regex layer rejects, the
        composed lint must still reject — the backstop cannot rescue it.
        """
        regex_caught = [t for t in (EVASIVE_OVERCLAIMS + LEGITIMATE_TEXT +
                                    FORBIDDEN_CLAIM_ANCHORS) if regex_rejects(t)]
        self.assertTrue(regex_caught, "fixture no longer exercises the regex layer")
        lint = OverclaimLint()
        for text in regex_caught:
            with self.subTest(text=text[:60]):
                with self.assertRaises(OverclaimLintViolation):
                    lint.lint_text(text)

    def test_a_dead_backstop_leaves_the_regex_verdict_intact(self):
        """
        An unreachable or offline-uncached embedding surface must not change any
        verdict — the backstop degrades to exactly the behaviour that preceded
        it, rather than blocking or silently becoming the sole authority.
        """
        class DeadBackstop:
            def is_semantic_overclaim(self, text):
                return None

        lint = OverclaimLint(backstop=DeadBackstop())
        for text in LEGITIMATE_TEXT:
            with self.subTest(text=text[:60]):
                self.assertEqual(lint.lint_text(text), text)
        for text in FORBIDDEN_CLAIM_ANCHORS:
            if regex_rejects(text):
                with self.subTest(forbidden=text[:60]):
                    with self.assertRaises(OverclaimLintViolation):
                        lint.lint_text(text)


class BackstopCatchesWhatRegexesMissTest(unittest.TestCase):
    """The reason it exists: measured regex coverage is 4 of 12 paraphrases."""

    def setUp(self):
        self.backstop = SemanticBackstop()

    def test_evasive_paraphrases_are_caught(self):
        for text in EVASIVE_OVERCLAIMS:
            with self.subTest(text=text[:60]):
                self.assertFalse(regex_rejects(text),
                                 "probe no longer evades the regexes — pick a harder one")
                self.assertIsNotNone(
                    self.backstop.is_semantic_overclaim(text),
                    f"backstop failed to catch an evasive overclaim: {text!r}")

    def test_the_composed_lint_rejects_them(self):
        lint = OverclaimLint()
        for text in EVASIVE_OVERCLAIMS:
            with self.subTest(text=text[:60]):
                with self.assertRaises(OverclaimLintViolation):
                    lint.lint_text(text)


class NegationSurvivalTest(unittest.TestCase):
    """The failure this design was corrected for, pinned."""

    def setUp(self):
        self.backstop = SemanticBackstop()

    def test_negated_claims_are_not_refused(self):
        """
        "This revocation does not un-train the model" DENIES the forbidden claim
        while sitting close to it. Every drafted notice must contain that
        phrase, so refusing it would break notice drafting outright.
        """
        for text in LEGITIMATE_TEXT:
            with self.subTest(text=text[:60]):
                self.assertIsNone(
                    self.backstop.is_semantic_overclaim(text),
                    f"legitimate text was refused as an overclaim: {text!r}")

    def test_legitimate_text_passes_the_composed_lint(self):
        lint = OverclaimLint()
        for text in LEGITIMATE_TEXT:
            with self.subTest(text=text[:60]):
                self.assertEqual(lint.lint_text(text), text)

    def test_permitted_anchors_exist_and_are_distinct_from_forbidden(self):
        self.assertTrue(PERMITTED_CLAIM_ANCHORS)
        self.assertFalse(set(PERMITTED_CLAIM_ANCHORS) & set(FORBIDDEN_CLAIM_ANCHORS))

    def test_threshold_is_a_fixed_published_literal(self):
        """A threshold tuned per case is how a backstop becomes theatre."""
        self.assertIsInstance(SIMILARITY_THRESHOLD, float)
        self.assertGreater(SIMILARITY_THRESHOLD, 0.5)


class OfflineSafetyTest(unittest.TestCase):
    """`make demo` is credential-free; the backstop must never break that."""

    def test_offline_with_no_cached_vector_disables_the_backstop(self):
        prior = os.environ.get("HODI_OFFLINE")
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(
            lambda: os.environ.__setitem__("HODI_OFFLINE", prior) if prior is not None
            else os.environ.pop("HODI_OFFLINE", None))
        backstop = SemanticBackstop()
        novel = "an utterance no cache could possibly contain 8f3a1c published nowhere"
        self.assertIsNone(backstop.is_semantic_overclaim(novel),
                          "offline with no cached vector must disable the backstop, not guess")


if __name__ == "__main__":
    unittest.main()
