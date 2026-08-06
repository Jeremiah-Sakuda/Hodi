import unittest
from src.agents.rights_custodian import RightsCustodianAgent

class TestRightsCustodianIAM(unittest.TestCase):
    """
    Rights Custodian Conflict Boundary & Paired IAM Tests (HOD-310).
    """

    def setUp(self):
        self.agent = RightsCustodianAgent()

    def test_rights_custodian_can_read_works_and_artists(self):
        """Paired Positive: Rights Custodian CAN read works/ and artists/ collections."""
        res_works = self.agent.get_registered_works()
        self.assertEqual(res_works["status"], "SUCCESS")
        self.assertEqual(res_works["collection"], "works")

        res_artists = self.agent.get_artist_identity()
        self.assertEqual(res_artists["status"], "SUCCESS")
        self.assertEqual(res_artists["collection"], "artists")

    def test_rights_custodian_cannot_read_buyer_terms(self):
        """Paired Negative: Rights Custodian CANNOT read buyer_terms/ collection."""
        with self.assertRaises(PermissionError) as ctx:
            self.agent.read_buyer_terms("acme-corp")
        self.assertIn("PERMISSION_DENIED", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
