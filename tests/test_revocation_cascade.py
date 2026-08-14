import unittest
from datetime import datetime, timezone, timedelta
from src.schema.grant_event import GrantEvent, Scope
from src.schema.revocation import RevocationNotice
from src.gateway.gateway import AgentGateway
from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.resolve.resolver import resolve
from tests.offline_env import force_offline

class TestRevocationCascade(unittest.TestCase):
    def setUp(self):
        # This is a UNIT test over in-memory events. Force the offline gateway:
        # with real credentials present, a live gateway would WRITE revoked
        # events and notices into production Firestore (this happened once —
        # see BUILD-LOG 2026-08-07).
        import os
        force_offline(self)
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

    def test_revoking_training_terminates_only_grants_that_permit_training(self):
        # A grant is affected iff it PERMITS the revoked use. Revoking `training`
        # terminates g1 (a training grant). It must NOT terminate g2 — a
        # `fine_tuning`-only grant never permitted training, and the artist did
        # not revoke fine-tuning — nor g3 (`synthesis`, incomparable).
        #
        # This test asserted the opposite through 2026-08-10 ("g2 should be
        # revoked"), which is the over-revocation the cascade-direction bug
        # produced: destroying a license for a use that was never revoked.
        result = self.propagator.execute_revocation_cascade(work_id="w1", revoked_use_type="training")

        self.assertEqual(result.revoked_use_type, "training")
        # derived_scopes still describes what a terminated *training* grant loses.
        self.assertEqual(set(result.derived_scopes),
                         {"training", "fine_tuning", "rag_retrieval", "human_reference"})

        affected_ids = [ag.grant_id for ag in result.affected_grants]
        self.assertIn("g1", affected_ids)
        self.assertNotIn("g2", affected_ids)   # fine_tuning grant: never permitted training
        self.assertNotIn("g3", affected_ids)   # synthesis: incomparable

        self.assertEqual(resolve("g1", events=self.events).status, "revoked")
        self.assertEqual(resolve("g2", events=self.events).status, "active")
        self.assertIsNotNone(resolve("g2", events=self.events).active_scope)
        self.assertEqual(resolve("g3", events=self.events).status, "active")

        # The one terminated grant keeps its full append-only history.
        self.assertEqual(len(resolve("g1", events=self.events).history_events), 2)

    def test_revoking_fine_tuning_terminates_the_broader_training_grant_too(self):
        # The other direction, the one the old rule under-reached: revoking
        # `fine_tuning` must terminate BOTH g2 (a fine_tuning grant) and g1 (a
        # training grant, which permits fine-tuning) — otherwise the training
        # buyer keeps fine-tuning after it was revoked. g3 (synthesis) is
        # untouched. Terminating g1 wholesale also strips its training right,
        # which the artist did not revoke: that is the disclosed inexpressibility
        # limit (a chain scope cannot say "training but not fine_tuning"), and it
        # is the safe direction — better to over-strip a grant that permitted the
        # revoked use than to leave the revoked use available.
        result = self.propagator.execute_revocation_cascade(work_id="w1", revoked_use_type="fine_tuning")

        affected_ids = [ag.grant_id for ag in result.affected_grants]
        self.assertIn("g1", affected_ids)
        self.assertIn("g2", affected_ids)
        self.assertNotIn("g3", affected_ids)
        self.assertEqual(resolve("g1", events=self.events).status, "revoked")
        self.assertEqual(resolve("g2", events=self.events).status, "revoked")
        self.assertEqual(resolve("g3", events=self.events).status, "active")
        
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


class TestDerivationMatchesTheLattice(unittest.TestCase):
    """
    The cascade's downstream derivation must agree with the lattice for EVERY
    use-type (HOD-104, HOD-350).

    `RevocationPropagatorAgent` used to re-implement the partial order as an
    if/elif ladder — a second source of truth that `lattice.py` exists to
    prevent, and a correctness risk rather than a style one, because the
    cascade computes downstream scopes from it. Adding a use-type to the
    lattice would have silently produced an incomplete cascade.
    """

    def setUp(self):
        import os
        force_offline(self)
        self.propagator = RevocationPropagatorAgent(gateway=AgentGateway(), memory_bank_events=[])

    def test_derivation_matches_is_use_type_contained_across_the_full_order(self):
        from src.schema.lattice import USE_TYPE_CONTAINMENT, is_use_type_contained
        for use_type in USE_TYPE_CONTAINMENT:
            with self.subTest(use_type=use_type):
                result = self.propagator.execute_revocation_cascade(
                    work_id="work-no-grants", revoked_use_type=use_type)
                derived = {d.scope for d in result.structured_derivation}
                expected = {u for u in USE_TYPE_CONTAINMENT if is_use_type_contained(use_type, u)}
                self.assertEqual(
                    derived, expected,
                    f"cascade derivation for '{use_type}' disagrees with the lattice")
                self.assertEqual(set(result.derived_scopes), expected)

    def test_every_derivation_step_is_a_real_containment_edge(self):
        from src.schema.lattice import USE_TYPE_CONTAINMENT, is_use_type_contained
        for use_type in USE_TYPE_CONTAINMENT:
            result = self.propagator.execute_revocation_cascade(
                work_id="work-no-grants", revoked_use_type=use_type)
            for step in result.structured_derivation:
                with self.subTest(use_type=use_type, step=step.scope):
                    self.assertTrue(
                        is_use_type_contained(step.parent, step.scope),
                        f"'{step.parent}' does not contain '{step.scope}' in the lattice")

    def test_synthesis_cascades_to_itself_only(self):
        """`synthesis` is incomparable to the training chain — a revocation of it
        must not reach any other use-type."""
        result = self.propagator.execute_revocation_cascade(
            work_id="work-no-grants", revoked_use_type="synthesis")
        self.assertEqual([d.scope for d in result.structured_derivation], ["synthesis"])

    def test_a_new_use_type_would_be_picked_up_without_touching_the_agent(self):
        """The property the if/elif ladder broke: the agent reads the order, it
        does not restate it."""
        import src.schema.lattice as lattice
        original = dict(lattice.USE_TYPE_CONTAINMENT)
        try:
            lattice.USE_TYPE_CONTAINMENT["training"] = original["training"] | {"speculative_use"}
            lattice.USE_TYPE_CONTAINMENT["speculative_use"] = {"speculative_use"}
            result = self.propagator.execute_revocation_cascade(
                work_id="work-no-grants", revoked_use_type="training")
            self.assertIn("speculative_use", {d.scope for d in result.structured_derivation})
        finally:
            lattice.USE_TYPE_CONTAINMENT.clear()
            lattice.USE_TYPE_CONTAINMENT.update(original)
