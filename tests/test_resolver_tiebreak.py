"""
Determinism tiebreak coverage (HOD-103).

`resolve()` sorts by `(issued_at, event_id)` and the comment above that line
says changing it "breaks historical reproducibility." Nothing tested it:
weakening the sort to `issued_at` alone left all tests and `make demo` passing,
because every fixture event carried a DISTINCT `issued_at`, so the tiebreak was
dead coverage.

These fixtures deliberately share one timestamp. Without the `event_id`
tiebreak, the same event set folds to a different final state depending on the
order it happens to arrive in — which is precisely the property the comment
claims to defend.
"""

import unittest
from datetime import datetime, timezone
from itertools import permutations

from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope
from src.resolve.resolver import resolve

SAME_INSTANT = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


def event(event_id: str, kind: str, use_type: str = "training") -> GrantEvent:
    """All events share SAME_INSTANT, so only event_id can order them."""
    return GrantEvent(
        event_id=event_id,
        grant_id="grant-tie",
        work_id="work-tie",
        counterparty_id="buyer-tie",
        scope=Scope(use_type=use_type, valid_from=SAME_INSTANT),
        kind=kind,
        issued_at=SAME_INSTANT,
        signature=f"sig-{event_id}",
    )


class TestSameTimestampTiebreak(unittest.TestCase):
    def setUp(self):
        # Deliberately NOT in event_id order, so a stable sort on issued_at
        # alone would preserve this (wrong) input order.
        self.events = [
            event("evt-c-granted", "granted", "fine_tuning"),
            event("evt-a-granted", "granted", "training"),
            event("evt-b-revoked", "revoked"),
        ]

    def test_fold_is_identical_under_every_input_ordering(self):
        """The property: with identical timestamps, the fold must still be
        order-independent. Only the event_id tiebreak makes that true."""
        results = {
            resolve("grant-tie", events=list(order)).model_dump_json()
            for order in permutations(self.events)
        }
        self.assertEqual(len(results), 1,
                         f"same-timestamp events folded to {len(results)} different states "
                         "depending on input order — the (issued_at, event_id) tiebreak is broken")

    def test_tiebreak_orders_by_event_id_so_the_last_event_is_deterministic(self):
        """Sorted by event_id at equal timestamps, 'evt-c-granted' is last, so
        the grant resolves ACTIVE — not to whichever event arrived last."""
        state = resolve("grant-tie", events=list(self.events))
        self.assertEqual(state.last_event_id, "evt-c-granted")
        self.assertEqual(state.status, "active")
        self.assertEqual(state.active_scope.use_type, "fine_tuning")

    def test_all_same_timestamp_events_remain_visible(self):
        state = resolve("grant-tie", events=list(self.events))
        self.assertEqual(len(state.history_events), 3)


if __name__ == "__main__":
    unittest.main()
