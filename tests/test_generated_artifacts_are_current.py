"""
tests/test_generated_artifacts_are_current.py — a generated artifact must not be
older than the source it is generated from (HOD-741).

THE DEFECT THIS EXISTS FOR. `diagram_b_what_hodi_will_not_say.png` is the image
the README puts on its landing page, the one the recording script holds
FULL-SCREEN for a beat marked "never cut", and the attachment on a social post.
Its own title bar reads *"every number on this diagram is read from
/docs/metrics.json."* For fourteen days it read `539 records accrued · 0
known-crawler user agents` while its `.mmd` source — and the metrics file, and
the README, and the narration spoken over it — said thousands of records and a
non-zero crawler count.

`check_doc_metrics.py` could not see it: it binds `DIAGRAM_B` to the `.mmd` and
then prints that "Diagram B agrees with docs/metrics.json". The source agreed.
The image nobody regenerated did not, and the guard's success message named the
artifact it had not checked.

This is the fourth instance of the same shape in this project — the conflict
matrix, the README deployment table, the recording script's predicted timing,
and now the diagrams. Every one was a file marked GENERATED that nothing
regenerated and nothing compared. Checking a byte-level match would require the
renderer in CI, so this checks the property that actually failed: **the render
is older than its source.**
"""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "docs" / "architecture"
RENDER_SUFFIXES = (".png", ".svg")


def git_commit_epoch(path: Path) -> int:
    """
    Last commit time, not filesystem mtime.

    A fresh `git clone` writes every file at checkout time, so mtimes are
    identical and a mtime comparison would pass vacuously in CI — which is
    precisely where this needs to fail.
    """
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True)
    return int(out.stdout.strip()) if out.stdout.strip() else 0


class RendersAreNotOlderThanTheirSourceTest(unittest.TestCase):

    def test_every_mermaid_source_has_renders(self):
        sources = sorted(ARCH.glob("*.mmd"))
        self.assertTrue(sources, "no .mmd sources found — this guard is checking nothing")
        for src in sources:
            for suffix in RENDER_SUFFIXES:
                render = src.with_suffix(suffix)
                self.assertTrue(render.exists(),
                                f"{src.name} has no {suffix} render, but the README embeds one")

    def test_no_render_predates_its_source(self):
        stale = []
        for src in sorted(ARCH.glob("*.mmd")):
            src_t = git_commit_epoch(src)
            for suffix in RENDER_SUFFIXES:
                render = src.with_suffix(suffix)
                if not render.exists():
                    continue
                render_t = git_commit_epoch(render)
                if src_t and render_t and render_t < src_t:
                    stale.append(
                        f"{render.name} was last committed {src_t - render_t}s BEFORE "
                        f"{src.name} — the image shows different numbers than its source")
        self.assertFalse(
            stale,
            "a generated diagram is older than the source it is generated from. The README "
            "embeds these images and the recording script holds one full-screen:\n  "
            + "\n  ".join(stale)
            + "\n  Re-render with: npx -y @mermaid-js/mermaid-cli@11 -i <file>.mmd -o <file>.png -b white")


class TheConflictMatrixIsRegeneratedNotRememberedTest(unittest.TestCase):
    """
    The README says this document "cannot drift from the enforced bindings".
    It had drifted by one line — generated once, then left behind.
    """

    def test_regenerating_the_matrix_produces_no_diff(self):
        matrix = ROOT / "docs" / "architecture" / "conflict_matrix.md"
        before = matrix.read_text()
        try:
            subprocess.run(["python3", "scripts/generate_conflict_matrix.py"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
            after = matrix.read_text()
        finally:
            if matrix.read_text() != before:
                matrix.write_text(before)  # never leave the tree dirty
        self.assertEqual(
            before, after,
            "docs/architecture/conflict_matrix.md differs from what "
            "scripts/generate_conflict_matrix.py produces from src/schema/iam_policy.py. The README "
            "states this document cannot drift; regenerate and commit it.")


if __name__ == "__main__":
    unittest.main()
