import unittest
from datetime import datetime, timezone, timedelta
from src.schema.grant_event import GrantEvent, Scope
from src.schema.revocation import RevocationNotice
from src.gateway.gateway import AgentGateway
from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.resolve.resolver import resolve

class TestRevocationCascade(unittest.TestCase):
    def setUp(self):
        self.gateway = AgentGateway()
        
        self.t0 = datetime.now(timezone.utc) - timedelta(days=2)
        
        # Create a work with multiple active grants
        self.events = [
            # Grant 1: 'training'
            GrantEvent(
                event_id="e1", grant_id="g1", work_id="w1", counterparty_id="buyer1",
                scope=Scope(use_type="training", model_class="all_models", derivative_retention=True, attribution_required=True, commercial=True, valid_from=self.t0, valid_until=None),
                kind="granted", issued_at=self.t0, signature="sig1"
            ),
            # Grant 2: 'fine_tuning' (subset of training)
            GrantEvent(
                event_id="e2", grant_id="g2", work_id="w1", counterparty_id="buyer2",
                scope=Scope(use_type="fine_tuning", model_class="open_weights", derivative_retention=False, attribution_required=True, commercial=False, valid_from=self.t0, valid_until=None),
                kind="granted", issued_at=self.t0, signature="sig2"
            ),
            # Grant 3: 'synthesis' (independent of training)
            GrantEvent(
                event_id="e3", grant_id="g3", work_id="w1", counterparty_id="buyer3",
                scope=Scope(use_type="synthesis", model_class="all_models", derivative_retention=True, attribution_required=True, commercial=True, valid_from=self.t0, valid_until=None),
                kind="granted", issued_at=self.t0, signature="sig3"
            )
        ]
        self.propagator = RevocationPropagatorAgent(gateway=self.gateway, memory_bank_events=self.events)

    def test_revocation_lattice_containment(self):
        # Revoking 'training' should cascade to 'training', 'fine_tuning', 'rag_retrieval', 'human_reference'
        # So g1 and g2 should be revoked. g3 (synthesis) should NOT be revoked.
        
        result = self.propagator.execute_revocation_cascade(work_id="w1", revoked_use_type="training")
        
        self.assertEqual(result.revoked_use_type, "training")
        self.assertIn("training", result.derived_scopes)
        self.assertIn("fine_tuning", result.derived_scopes)
        self.assertIn("rag_retrieval", result.derived_scopes)
        self.assertIn("human_reference", result.derived_scopes)
        
        affected_ids = [ag.grant_id for ag in result.affected_grants]
        self.assertIn("g1", affected_ids)
        self.assertIn("g2", affected_ids)
        self.assertNotIn("g3", affected_ids)
        
        # Check current state
        state_g1 = resolve("g1", events=self.events)
        self.assertEqual(state_g1.status, "revoked")
        self.assertIsNone(state_g1.active_scope)
        
        state_g2 = resolve("g2", events=self.events)
        self.assertEqual(state_g2.status, "revoked")
        self.assertIsNone(state_g2.active_scope)
        
        state_g3 = resolve("g3", events=self.events)
        self.assertEqual(state_g3.status, "active")
        self.assertIsNotNone(state_g3.active_scope)
        
        # Check that original grants are still in history (never deleted)
        self.assertEqual(len(state_g1.history_events), 2) # granted + revoked
        self.assertEqual(len(state_g2.history_events), 2)
        
    def test_temporal_stability_after_revocation(self):
        # Revoke 'training'
        t_before = self.t0 + timedelta(days=1)
        
        result = self.propagator.execute_revocation_cascade(work_id="w1", revoked_use_type="training")
        
        # Current state is revoked
        state_now = resolve("g1", events=self.events)
        self.assertEqual(state_now.status, "revoked")
        
        # Querying the past (t_before) must remain UNCHANGED
        state_past = resolve("g1", at=t_before, events=self.events)
        self.assertEqual(state_past.status, "active")
        self.assertEqual(state_past.active_scope.use_type, "training")

if __name__ == '__main__':
    unittest.main()
