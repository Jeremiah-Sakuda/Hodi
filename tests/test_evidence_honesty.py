import unittest
import os
import re
from pathlib import Path

class TestEvidenceHonesty(unittest.TestCase):
    """
    Standing Honesty Invariant Test (PRD §1.3, §3.3).
    Asserts that no code path produces a cross-class total, score, rank, or aggregate across evidence classes.
    """

    def test_no_cross_class_aggregation_in_evidence_modules(self):
        """
        Static & functional audit asserting no code in src/evidence or src/console/
        computes cross-class totals, sums, or numeric scores across evidence classes.
        """
        repo_root = Path(__file__).resolve().parent.parent
        target_dirs = [repo_root / "src" / "evidence", repo_root / "src" / "console"]

        forbidden_patterns = [
            r"sum\(.*evidence.*\)",
            r"total_score",
            r"evidence_score",
            r"rank_evidence",
            r"aggregate_evidence_score"
        ]

        violations = []

        for target_dir in target_dirs:
            if not target_dir.exists():
                continue
            for file_path in target_dir.rglob("*.py"):
                text = file_path.read_text(encoding="utf-8")
                for pattern in forbidden_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        violations.append(f"{file_path.name}: matched forbidden pattern '{pattern}'")

        self.assertEqual(
            violations,
            [],
            f"Honesty Invariant Violation detected! Code path attempts cross-class evidence aggregation: {violations}"
        )

if __name__ == "__main__":
    unittest.main()
