import unittest
import os
import re
from pathlib import Path
from src.evidence.evidence_engine import EvidenceEngine

class TestEvidenceHonesty(unittest.TestCase):
    """
    Standing Honesty Invariant Test (PRD §1.3, §3.3).
    Asserts that no code path produces a cross-class total, score, rank, or aggregate across evidence classes.
    """

    def test_no_cross_class_aggregation_in_evidence_modules(self):
        """
        Static audit asserting no code in src/evidence or src/console/
        computes cross-class totals, sums, or numeric scores across evidence classes.
        """
        repo_root = Path(__file__).resolve().parent.parent
        target_dirs = [repo_root / "src" / "evidence", repo_root / "src" / "console"]

        forbidden_patterns = [
            r"sum\(.*evidence.*\)",
            r"total_score",
            r"evidence_score",
            r"rank_evidence",
            r"aggregate_evidence_score",
            r"total_evidence_count",
            r"combine_evidence"
        ]

        violations = []
        scanned = []

        for target_dir in target_dirs:
            if not target_dir.exists():
                continue
            for ext in ["*.py", "*.js", "*.html"]:
                for file_path in target_dir.rglob(ext):
                    text = file_path.read_text(encoding="utf-8")
                    # The pattern loop was dedented one level, so `text` held only
                    # the LAST file each glob yielded and roughly four of five
                    # files in src/evidence were never scanned at all.
                    for pattern in forbidden_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            violations.append(
                                f"{file_path.name}: matched forbidden pattern '{pattern}'")
                    scanned.append(file_path.name)

        self.assertEqual(
            violations,
            [],
            f"Honesty Invariant Violation detected! Code path attempts cross-class evidence aggregation: {violations}"
        )
        # Guard the guard: this passed for weeks while inspecting ONE file per
        # glob, because the pattern loop sat outside the file loop. Assert the
        # scan covered every file that exists, not an arbitrary floor.
        expected = sorted(
            f.name for d in target_dirs if d.exists()
            for ext in ["*.py", "*.js", "*.html"] for f in d.rglob(ext)
        )
        self.assertEqual(
            sorted(scanned), expected,
            f"static audit inspected {len(scanned)} of {len(expected)} files — it is not scanning the tree")

    def test_functional_evidence_engine_exposes_no_cross_class_aggregators(self):
        """
        Functional audit of EvidenceEngine class methods to ensure no cross-class scoring,
        ordering, or total sum methods exist on the object.
        """
        engine = EvidenceEngine()
        method_names = [m for m in dir(engine) if not m.startswith("_")]

        forbidden_keywords = ["total", "sum", "score", "rank", "aggregate", "combine"]
        for m in method_names:
            for kw in forbidden_keywords:
                self.assertNotIn(
                    kw,
                    m.lower(),
                    f"Honesty Invariant Violation: EvidenceEngine method '{m}' contains forbidden aggregation keyword '{kw}'."
                )

    def test_no_hardcoded_metric_literals_in_console(self):
        """
        HOD-370: Console must not render fabricated evidence numbers.
        Any numeric literal assigned to a metric field in the console UI
        violates the honesty invariant.
        """
        repo_root = Path(__file__).resolve().parent.parent
        console_dir = repo_root / "src" / "console"
        
        # Matches property assignments like: count: 47, latency: 120, records: 0
        violation_pattern = re.compile(r'(count|latency|records|total|accrued)\s*:\s*\d+', re.IGNORECASE)
        
        violations = []
        if console_dir.exists():
            for ext in ["*.js", "*.html"]:
                for file_path in console_dir.rglob(ext):
                    lines = file_path.read_text(encoding="utf-8").splitlines()
                    for i, line in enumerate(lines):
                        if violation_pattern.search(line):
                            violations.append(f"{file_path.name}:{i+1}: {line.strip()}")
        
        self.assertEqual(
            violations,
            [],
            f"Honesty Invariant Violation detected! Found hardcoded metric literals in console code:\n" + "\n".join(violations)
        )

if __name__ == "__main__":
    unittest.main()
