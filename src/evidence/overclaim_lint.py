import re
from typing import List

class OverclaimLintViolation(Exception):
    """Raised when generated text or render payload violates the overclaim honesty invariant."""
    pass

class OverclaimLint:
    """
    Render-Time Overclaim Lint (HOD-320 / Invariants 1 & 2).
    Rejects any text that asserts model training, training-set membership,
    or model ingestion proof.
    """

    FORBIDDEN_PHRASES = [
        r"trained\s+on",
        r"was\s+in\s+the\s+training\s+set",
        r"proves?\s+training",
        r"proves?\s+the\s+model\s+saw",
        r"your\s+(art|work|content|essay|repo|music)\s+is\s+inside",
        r"proves?\s+ingestion",
        r"in\s+(the|a)\s+training\s+dataset",
        r"model\s+has\s+memorized",
        r"proves?\s+membership"
    ]

    def lint_text(self, text: str) -> str:
        """
        Lints text for overclaim violations.
        Raises OverclaimLintViolation if any forbidden phrase or paraphrase is detected.
        Returns the original text clean if no violation found.
        """
        text_lower = text.lower()
        for pattern in self.FORBIDDEN_PHRASES:
            match = re.search(pattern, text_lower)
            if match:
                raise OverclaimLintViolation(
                    f"Honesty Invariant Violation: Generated text contains overclaim assertion "
                    f"matching forbidden pattern '{pattern}': '{match.group(0)}' in text: '{text}'"
                )
        return text
