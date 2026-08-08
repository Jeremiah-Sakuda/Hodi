import unittest
from datetime import datetime, timezone, timedelta
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent, generate_deterministic_event_id
from src.resolve.resolver import resolve

class TestRevocationTemporalInteraction(unittest.TestCase):
    """
    HOD-107 Revocation & Temporal Interaction Test.
    Proves property: revocation narrows the present without rewriting the past.
    The same query at two timestamps returns different, individually correct answers, with both events visible.
    """

    def setUp(self):
        self.t_before = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)
        self.t_revoke = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.t_after = datetime(2026, 8, 20, 14, 0, 0, tzinfo=timezone.utc)

        self.scope_original = Scope(
            use_type="training",
            commercial=True,
            territory=["WW"],
            valid_from=self.t_before
        )

        self.scope_narrow = Scope(
            use_type="fine_tuning",
            commercial=False,
            territory=["US"],
            valid_from=self.t_after
        )

        self.grant_event = GrantEvent(
            event_id=generate_deterministic_event_id("grant-rev-200", 1, 1),
            grant_id="grant-rev-200",
            work_id="work-essay-001",
            counterparty_id="buyer-scraper-corp",
            scope=self.scope_original,
            kind="granted",
            issued_at=self.t_before,
            signature="sig-grant"
        )

        self.revoke_event = GrantEvent(
            event_id=generate_deterministic_event_id("grant-rev-200", 2, 1),
            grant_id="grant-rev-200",
            work_id="work-essay-001",
            counterparty_id="buyer-scraper-corp",
            scope=self.scope_original,
            kind="revoked",
            issued_at=self.t_revoke,
            signature="sig-revoke"
        )

        self.regrant_event = GrantEvent(
            event_id=generate_deterministic_event_id("grant-rev-200", 3, 1),
            grant_id="grant-rev-200",
            work_id="work-essay-001",
            counterparty_id="buyer-scraper-corp",
            scope=self.scope_narrow,
            # A re-grant is a NEW `granted` event. `superseded` marks a grant as
            # history and grants nothing — see test_superseded_semantics.py.
            kind="granted",
            supersedes="grant-rev-200",
            issued_at=self.t_after,
            signature="sig-regrant"
        )

        self.log = [self.grant_event, self.revoke_event, self.regrant_event]

    def test_mid_term_revocation_leaves_past_unchanged(self):
        """Querying at t_before returns original granted state."""
        state_before = resolve("grant-rev-200", at=self.t_before, events=self.log)
        self.assertEqual(state_before.status, "active")
        self.assertEqual(state_before.active_scope.use_type, "training")
        self.assertTrue(state_before.active_scope.commercial)
        self.assertEqual(len(state_before.history_events), 1)

    def test_revocation_at_t_revoke_terminates_grant(self):
        """Querying at t_revoke returns revoked state with active_scope None."""
        state_revoke = resolve("grant-rev-200", at=self.t_revoke, events=self.log)
        self.assertEqual(state_revoke.status, "revoked")
        self.assertIsNone(state_revoke.active_scope)
        self.assertEqual(len(state_revoke.history_events), 2)

    def test_regrant_narrower_resolves_to_narrower_scope(self):
        """Querying at t_after returns narrower scope and preserves full event log visibility."""
        state_after = resolve("grant-rev-200", at=self.t_after, events=self.log)
        self.assertEqual(state_after.status, "active")
        self.assertEqual(state_after.active_scope.use_type, "fine_tuning")
        self.assertFalse(state_after.active_scope.commercial)
        self.assertEqual(len(state_after.history_events), 3)

        # Confirm all 3 historical events remain visible in append-only log
        event_kinds = [e.kind for e in state_after.history_events]
        self.assertEqual(event_kinds, ["granted", "revoked", "granted"])

if __name__ == "__main__":
    unittest.main()
