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
        """Paired Positive: Negotiator CAN read its own session counterparty's buyer terms,
        and the read is actually scoped by the enforced session filter."""
        res = self.agent.get_session_buyer_terms()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["collection"], "buyer_terms")
        self.assertEqual(res["enforced_filter_key"], "counterparty_id")
        self.assertEqual(res["enforced_filters"], {"counterparty_id": self.session_id})

    def test_negotiator_cannot_read_other_counterparty_buyer_terms(self):
        """Paired Negative: Negotiator CANNOT read another counterparty's buyer terms."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.get_other_buyer_terms("buyer-session-rival-corp")
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

    def test_negotiator_cannot_read_buyer_terms_unfiltered(self):
        """Paired Negative: a collection-wide read with no session filter is denied.
        This is the hole the old prefix matcher opened (BUILD-LOG 2026-08-07)."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.get_unfiltered_buyer_terms()
        self.assertIn("MUST scope its query", str(ctx.exception))

    def test_negotiator_cannot_read_artist_identity(self):
        """Paired Negative: Negotiator CANNOT read artist identity."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_artist_identity()
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
