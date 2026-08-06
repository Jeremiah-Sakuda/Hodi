import unittest
from src.agents.licensing_negotiator import LicensingNegotiatorAgent

class TestLicensingNegotiatorIAM(unittest.TestCase):
    """
    Licensing Negotiator Confidentiality & Paired IAM Tests (HOD-311).
    """

    def setUp(self):
        self.session_id = "buyer-session-acme"
        self.agent = LicensingNegotiatorAgent(session_counterparty_id=self.session_id)

    def test_negotiator_can_read_own_session_buyer_terms(self):
        """Paired Positive: Negotiator CAN read its own session counterparty's buyer terms."""
        res = self.agent.get_session_buyer_terms()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn(self.session_id, res["collection"])

    def test_negotiator_cannot_read_other_counterparty_buyer_terms(self):
        """Paired Negative: Negotiator CANNOT read another counterparty's buyer terms."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.get_other_buyer_terms("buyer-session-rival-corp")
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

    def test_negotiator_cannot_read_artist_identity(self):
        """Paired Negative: Negotiator CANNOT read artist identity."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_artist_identity()
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
