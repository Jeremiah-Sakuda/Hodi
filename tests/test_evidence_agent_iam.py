import unittest
from src.agents.evidence_agent import EvidenceAgent

class TestEvidenceAgentIAM(unittest.TestCase):
    """
    Evidence Agent Conflict Boundary & Paired IAM Tests (HOD-320).
    """

    def setUp(self):
        self.agent = EvidenceAgent()

    def test_evidence_agent_can_read_crawler_logs_and_canaries(self):
        """Paired Positive: Evidence Agent CAN read crawler_access/ and canaries/ collections."""
        res_logs = self.agent.get_crawler_access_logs()
        self.assertEqual(res_logs["status"], "SUCCESS")

        res_canaries = self.agent.get_canary_records()
        self.assertEqual(res_canaries["status"], "SUCCESS")

    def test_evidence_agent_cannot_read_buyer_terms(self):
        """Paired Negative: Evidence Agent CANNOT read buyer_terms/ collection."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_buyer_terms("acme-corp")
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

    def test_evidence_agent_cannot_read_artist_identity(self):
        """Paired Negative: Evidence Agent CANNOT read artist identity."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_artist_identity()
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
