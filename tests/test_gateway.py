import unittest
from src.gateway.gateway import AgentGateway
from tests.offline_env import force_offline

class TestAgentGateway(unittest.TestCase):
    """
    Agent Gateway Routing & Non-Silent Denial Tests (HOD-312).
    """

    def setUp(self):
        # Unit test: force the offline gateway so permitted routes never touch
        # live Firestore, regardless of ambient credentials.
        import os
        force_offline(self)
        self.gateway = AgentGateway()

    def test_authorized_gateway_route_succeeds(self):
        """Authorized call routes successfully through Gateway."""
        res = self.gateway.route(
            calling_sa="rights-custodian-sa@hodi-2026.iam.gserviceaccount.com",
            calling_role_key="rights_custodian",
            target_collection="works",
            payload={"query": "essay-001"}
        )
        self.assertEqual(res["status"], "ROUTED")

    def test_unauthorized_gateway_route_logs_event_and_raises_denial(self):
        """
        Unauthorized cross-boundary call raises GATEWAY_POLICY_DENIAL
        and logs PolicyDenialEvent (NEVER SILENT!).
        """
        with self.assertRaises(PermissionError) as ctx:
            self.gateway.route(
                calling_sa="licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com",
                calling_role_key="licensing_negotiator",
                target_collection="artists",
                payload={"query": "artist-id"}
            )
        self.assertIn("GATEWAY_POLICY_DENIAL", str(ctx.exception))
        self.assertEqual(len(self.gateway.denial_events), 1)

        event = self.gateway.denial_events[0]
        self.assertEqual(event.target_role, "licensing_negotiator")
        self.assertEqual(event.requested_collection, "artists")
        self.assertEqual(event.outcome, "DENIED")

if __name__ == "__main__":
    unittest.main()
