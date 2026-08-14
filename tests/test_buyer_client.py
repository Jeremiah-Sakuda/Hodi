"""
A second system honours the revocation (HOD-719).

The property under test: an outside buyer that verifies receipts with only
Hodi's public key STOPS using a work once the artist revokes — and its own
gate refuses too, without asking Hodi again.

The gap this closes, named by an external review: nothing demonstrated that
another system actually honours the terms. Hodi terminating a grant in its
own log is administration; a counterparty stopping is the product.

Run as a subprocess so the buyer really is a separate program with its own
main(), not a function call dressed up as one.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestBuyerClientHonoursRevocation(unittest.TestCase):
    def test_the_buyer_verifies_then_stops(self):
        env = dict(os.environ, HODI_OFFLINE="1", HODI_SIGNING="ephemeral")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "buyer_client.py")],
                                capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(result.returncode, 0,
                         f"buyer client failed:\n{result.stdout[-2000:]}\n{result.stderr[-1000:]}")
        out = result.stdout
        self.assertIn("receipt signature verifies", out)
        self.assertIn("the buyer STOPS using", out)
        self.assertIn("A SECOND SYSTEM HONOURED THE REVOCATION", out)
        # The honest limit travels with the demonstration.
        self.assertIn("did not and cannot un-train any model", out)


if __name__ == "__main__":
    unittest.main()
