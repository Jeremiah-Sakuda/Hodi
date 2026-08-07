import unittest
from src.evidence.overclaim_lint import OverclaimLint, OverclaimLintViolation

class TestOverclaimLint(unittest.TestCase):
    """
    Render-Time Overclaim Lint Tests (HOD-320).
    Seeded from paraphrases NOT in the lint's token list to prove non-cooperative overclaim detection.
    """

    def setUp(self):
        self.lint = OverclaimLint()

    def test_lint_passes_honest_evidence_claims(self):
        """Honest evidence descriptions pass without error."""
        clean_descriptions = [
            "Bot user-agent GPTBot fetched /works/essay-001 at 2026-08-06T17:32:36Z.",
            "Planted canary string HODI-CANARY-20260806-PROSE-9F81A2B3C4 detected in third-party dump.",
            "Verbatim 40-character substring match found in completion payload.",
            "Third-party site re-hosting registered work without valid license receipt."
        ]
        for desc in clean_descriptions:
            result = self.lint.lint_text(desc)
            self.assertEqual(result, desc)

    def test_lint_rejects_overclaim_paraphrases(self):
        """
        CRITICAL TEST: Seeded from paraphrases NOT in the lint's exact token list.
        Asserts OverclaimLintViolation is raised for any overclaiming statement.
        """
        unseen_overclaim_paraphrases = [
            "This log proves the model saw your work during training.",
            "Your art is inside GPT and was learned by the weights.",
            "Evidence shows this essay was in the training set.",
            "This canary hit proves training membership for your work.",
            "The model has memorized your entire repository from training."
        ]

        for paraphrase in unseen_overclaim_paraphrases:
            with self.assertRaises(OverclaimLintViolation, msg=f"Lint failed to reject paraphrase: '{paraphrase}'"):
                self.lint.lint_text(paraphrase)

if __name__ == "__main__":
    unittest.main()
