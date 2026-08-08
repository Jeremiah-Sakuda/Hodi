import unittest
import random
import json
from datetime import datetime, timezone, timedelta
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent, generate_deterministic_event_id
from src.resolve.resolver import resolve

class TestResolverReplay(unittest.TestCase):
    """
    HOD-103 Pure Fold & Replay Determinism Test.
    Proves that resolve(grant_id, at=t) over a shuffled event log returns byte-stable state.
    """

    def setUp(self):
        self.t1 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.t3 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)

        self.scope_broad = Scope(
            use_type="training",
            model_class="all_models",
            commercial=True,
            territory=["WW"],
            valid_from=self.t1
        )

        self.scope_narrow = Scope(
            use_type="fine_tuning",
            model_class="all_models",
            commercial=False,
            territory=["US"],
            valid_from=self.t3
        )

        # Construct deterministic event sequence
        self.event1 = GrantEvent(
            event_id=generate_deterministic_event_id("grant-100", 1, 1),
            grant_id="grant-100",
            work_id="work-01",
            counterparty_id="buyer-acme",
            scope=self.scope_broad,
            kind="granted",
            issued_at=self.t1,
            signature="sig-1"
        )

        self.event2 = GrantEvent(
            event_id=generate_deterministic_event_id("grant-100", 2, 1),
            grant_id="grant-100",
            work_id="work-01",
            counterparty_id="buyer-acme",
            scope=self.scope_broad,
            kind="revoked",
            issued_at=self.t2,
            signature="sig-2"
        )

        self.event3 = GrantEvent(
            event_id=generate_deterministic_event_id("grant-100", 3, 1),
            grant_id="grant-100",
            work_id="work-01",
            counterparty_id="buyer-acme",
            scope=self.scope_narrow,
            # Re-grant after revocation is a new `granted` event (HOD-107).
            kind="granted",
            supersedes="grant-100",
            issued_at=self.t3,
            signature="sig-3"
        )

        self.canonical_log = [self.event1, self.event2, self.event3]

    def test_pure_fold_replay_over_shuffled_log_is_byte_stable(self):
        """HOD-103 AC: Replay over a shuffled fixture log with no credentials is byte-stable."""
        canonical_state = resolve("grant-100", at=self.t3, events=self.canonical_log)
        canonical_json = canonical_state.model_dump_json(by_alias=True)

        # Shuffle event log 10 times and assert exact byte identity for resolved state
        rng = random.Random(42)
        for i in range(10):
            shuffled_log = list(self.canonical_log)
            rng.shuffle(shuffled_log)

            replayed_state = resolve("grant-100", at=self.t3, events=shuffled_log)
            replayed_json = replayed_state.model_dump_json(by_alias=True)

            self.assertEqual(
                canonical_json,
                replayed_json,
                f"Byte-stability failure on shuffle iteration {i}!"
            )

    def test_point_in_time_resolve_fold(self):
        """State at t1, t2, and t3 must return distinct, individually correct historical snapshots."""
        state_t1 = resolve("grant-100", at=self.t1, events=self.canonical_log)
        self.assertEqual(state_t1.status, "active")
        self.assertIsNotNone(state_t1.active_scope)
        self.assertEqual(state_t1.active_scope.use_type, "training")

        state_t2 = resolve("grant-100", at=self.t2, events=self.canonical_log)
        self.assertEqual(state_t2.status, "revoked")
        self.assertIsNone(state_t2.active_scope)

        state_t3 = resolve("grant-100", at=self.t3, events=self.canonical_log)
        self.assertEqual(state_t3.status, "active")
        self.assertIsNotNone(state_t3.active_scope)
        self.assertEqual(state_t3.active_scope.use_type, "fine_tuning")

if __name__ == "__main__":
    unittest.main()
