import unittest
from src.agents.revocation_propagator import RevocationPropagatorAgent

class TestRevocationPropagatorIAM(unittest.TestCase):
    """
    Revocation Propagator Conflict Boundary & Paired IAM Tests (HOD-350 / Correction 3).
    """

    def setUp(self):
        from src.gateway.gateway import AgentGateway
        self.gateway = AgentGateway()
        self.agent = RevocationPropagatorAgent(gateway=self.gateway, memory_bank_events=[])

    def test_revocation_propagator_can_write_notices_and_grants(self):
        """Paired Positive: Revocation Propagator CAN write revocation_notices/ and read grants/."""
        res_grants = self.agent.get_grants()
        self.assertEqual(res_grants["status"], "SUCCESS")

        res_notice = self.agent.write_revocation_notice({"notice_id": "notice-rev-100"})
        self.assertEqual(res_notice["status"], "SUCCESS")
        self.assertIn("receipt", res_notice)

    def test_revocation_propagator_cannot_read_buyer_terms(self):
        """Paired Negative (Correction 3): Revocation Propagator CANNOT read buyer_terms/."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_buyer_terms("acme-corp")
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

    def test_revocation_propagator_cannot_read_artist_identity(self):
        """Paired Negative: Revocation Propagator CANNOT read artist identity."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_artist_identity()
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
