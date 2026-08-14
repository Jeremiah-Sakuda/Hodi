"""
The suite must not clobber its own declared mode (HOD-716).

`make test` sets HODI_OFFLINE=1 for the whole run. Twenty-five setUp blocks
used to end with `addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))`,
which does not restore the previous state — it deletes a variable the rest
of the suite depends on. The first such test to finish silently un-declared
offline mode for everything that ran afterwards.

It was invisible for as long as the gateway failed OPEN on a missing
Firestore client: a polluted test just got the in-memory path by accident,
for the wrong reason. Making storage fail closed turned it into eight
errors immediately — the pollution had been there all along.

This guard is the mechanism that replaces remembering: a test file may not
pop HODI_OFFLINE in a cleanup. Use tests/offline_env.py, which saves and
restores.
"""

import os
import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# `os.environ.pop("HODI_OFFLINE", ...)` appearing inside an addCleanup or a
# teardown is the shape that loses the outer value.
POP_IN_CLEANUP = re.compile(
    r"addCleanup\([^)]*os\.environ\.pop\(\s*[\"']HODI_OFFLINE", re.S)


class TestNoTestPopsTheOfflineFlag(unittest.TestCase):
    def test_no_cleanup_pops_hodi_offline(self):
        offenders = []
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            if path.name == Path(__file__).name:
                continue  # this file names the pattern in order to forbid it
            text = path.read_text()
            for match in POP_IN_CLEANUP.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
        self.assertEqual(
            offenders, [],
            "these cleanups pop HODI_OFFLINE instead of restoring it, which "
            "un-declares offline mode for every test that runs afterwards. Use "
            "`from tests.offline_env import force_offline; force_offline(self)`:\n  "
            + "\n  ".join(offenders))

    def test_the_helper_restores_a_pre_existing_value(self):
        from tests.offline_env import force_offline

        class Probe(unittest.TestCase):
            def runTest(self):  # noqa: N802 — unittest naming
                force_offline(self)

        os.environ["HODI_OFFLINE"] = "1"
        probe = Probe()
        probe.run(unittest.TestResult())
        self.assertEqual(os.environ.get("HODI_OFFLINE"), "1",
                         "force_offline destroyed the suite-level declaration")

    def test_the_helper_removes_a_value_it_introduced(self):
        from tests.offline_env import force_offline

        class Probe(unittest.TestCase):
            def runTest(self):  # noqa: N802
                force_offline(self)

        saved = os.environ.pop("HODI_OFFLINE", None)
        try:
            Probe().run(unittest.TestResult())
            self.assertIsNone(os.environ.get("HODI_OFFLINE"),
                              "force_offline left the flag set for a run that never had it")
        finally:
            if saved is not None:
                os.environ["HODI_OFFLINE"] = saved


if __name__ == "__main__":
    unittest.main()
