"""
The red-team drill is a GUARD, not just a demo (HOD-712).

`make red-team` exits nonzero the instant any boundary yields. The count of
attacks is deliberately NOT pinned here — the exit code and the closing line
are the contract, so adding an attack does not require editing this guard. This test
runs it as a subprocess and asserts a clean exit, so a regression that
opens one of the five boundaries fails CI here — the same discipline the
project applies to every other structural guard.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestRedTeamDrill(unittest.TestCase):
    def test_all_boundaries_hold(self):
        env = dict(os.environ, HODI_OFFLINE="1")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "red_team.py")],
            capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(
            result.returncode, 0,
            f"red-team drill failed — a boundary yielded.\n"
            f"stdout tail:\n{result.stdout[-2000:]}\nstderr tail:\n{result.stderr[-1000:]}")
        self.assertIn("BOUNDARIES HELD", result.stdout)


if __name__ == "__main__":
    unittest.main()
