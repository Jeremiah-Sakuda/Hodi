"""
Revocation Propagator conflict boundary — paired IAM tests (HOD-350).

These now exercise the REAL Gateway policy path. They previously called four
hardcoded "mock method for IAM test" stubs on the agent that returned canned
values and raised a canned string, so they asserted against the stubs rather
than against the policy: the boundary could have been wide open and these tests
would still have passed. The stubs are gone; each method routes through the
Gateway under the propagator's own service account, so a denial here is the same
denial production would produce.
"""

import unittest

from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.schema.revocation import RevocationNotice
from datetime import datetime, timezone


class TestRevocationPropagatorIAM(unittest.TestCase):
    def setUp(self):
        # Unit test: force the offline gateway — the paired-positive case writes
        # a notice, and with real credentials that write would land in live Firestore.
        import os
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.gateway = AgentGateway()
        self.agent = RevocationPropagatorAgent(gateway=self.gateway, memory_bank_events=[])

    def test_propagator_can_read_grants_its_own_conflict_domain(self):
        """Paired positive: the read the propagator IS entitled to succeeds."""
        result = self.agent.get_grants(work_id="work-repo-001")
        self.assertEqual(result["status"], "SUCCESS")

    def test_propagator_can_deliver_a_revocation_notice(self):
        """Paired positive: writing to revocation_notices/ is permitted, and
        returns a receipt bound to the grant."""
        notice = RevocationNotice(
            grant_id="grant-iam-test",
            counterparty_id="buyer-iam-test",
            revoked_at=datetime.now(timezone.utc),
            notice_text=("This grant is hereby terminated. Please note that this revocation "
                         "terminates the legal license but does not un-train the model."),
        )
        receipt = self.gateway.deliver_revocation_notice(
            sender="revocation-propagator@hodi-2026.iam.gserviceaccount.com",
            counterparty_id="buyer-iam-test",
            notice=notice,
        )
        self.assertEqual(receipt.grant_id, "grant-iam-test")

    def test_propagator_cannot_read_buyer_terms(self):
        """Paired negative: denied BY POLICY, and logged as a structured event."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.agent.read_buyer_terms("acme-corp")
        self.assertIn("denied access to target collection 'buyer_terms'", str(ctx.exception))
        self.assertEqual(self.gateway.denial_events[-1].requested_collection, "buyer_terms")
        self.assertEqual(self.gateway.denial_events[-1].outcome, "DENIED")

    def test_propagator_cannot_read_artist_identity(self):
        """Paired negative: the propagator must not hold identity."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.agent.read_artist_identity()
        self.assertIn("denied access to target collection 'artists'", str(ctx.exception))
        self.assertEqual(self.gateway.denial_events[-1].requested_collection, "artists")

    def test_denials_are_the_same_exception_type_production_raises(self):
        """A denial here must not be a bespoke error the real path never emits."""
        with self.assertRaises(PermissionError):
            self.agent.read_artist_identity()
        self.assertTrue(issubclass(GatewayPolicyDenial, PermissionError))


if __name__ == "__main__":
    unittest.main()
