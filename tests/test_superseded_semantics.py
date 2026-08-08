"""
`superseded` means history, and all three components must agree (HOD-103, HOD-107).

The decided semantics: A SUPERSEDED GRANT IS NOT ACTIVE. IT IS HISTORY.
Same rule as revocation — the event stays in the append-only log, readable and
rendered struck through; it simply does not grant anything.

Before this was decided, three components gave three different answers about the
same event:

    resolve()              -> status="superseded" WITH a live active_scope
    active_grant_events()  -> [] (nothing active)          <- the correct answer
    permits() on raw events-> True (accepted kind="superseded")

Fail-closed, so never a breach, but "revocation is a new event that supersedes"
was not what the read path implemented. These tests assert the three agree, so
the three-answers state cannot return.
"""

import unittest
from datetime import datetime, timedelta, timezone

from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope
from src.resolve.resolver import resolve, active_grant_events
from src.resolve.evaluator import permits

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=1)
NOW = T0 + timedelta(days=5)

BROAD = Scope(use_type="training", model_class="all_models", commercial=True,
              territory=["WW"], valid_from=T0)
NARROW = Scope(use_type="fine_tuning", model_class="open_weights", commercial=False,
               territory=["US"], valid_from=T1)


def evt(event_id, kind, scope, issued_at, supersedes=None):
    return GrantEvent(event_id=event_id, grant_id="grant-sup", work_id="work-sup",
                      counterparty_id="buyer-sup", scope=scope, kind=kind,
                      supersedes=supersedes, issued_at=issued_at, signature=f"sig-{event_id}")


class TestSupersededIsHistory(unittest.TestCase):
    def setUp(self):
        self.log = [
            evt("e1", "granted", BROAD, T0),
            evt("e2", "superseded", BROAD, T1, supersedes="grant-sup"),
        ]

    def test_resolve_reports_superseded_with_no_active_scope(self):
        state = resolve("grant-sup", at=NOW, events=self.log)
        self.assertEqual(state.status, "superseded")
        self.assertIsNone(state.active_scope,
                          "a superseded grant must not hand back a live scope")

    def test_active_grant_events_returns_nothing(self):
        self.assertEqual(active_grant_events(self.log, at=NOW), [])

    def test_permits_refuses_raw_events_rather_than_filtering_them(self):
        """The door is closed, not filtered: permits() takes the folded active
        state. Passing raw append-only events is a programming error and must
        raise, not be silently skipped."""
        with self.assertRaises(ValueError) as ctx:
            permits(self.log, Scope(use_type="training", valid_from=NOW), at=NOW)
        self.assertIn("folded ACTIVE grant state", str(ctx.exception))

    def test_all_three_components_agree_nothing_is_permitted(self):
        """The regression this file exists for: one answer, three components."""
        state = resolve("grant-sup", at=NOW, events=self.log)
        active = active_grant_events(self.log, at=NOW)
        result = permits(active, Scope(use_type="training", valid_from=NOW), at=NOW)

        self.assertIsNone(state.active_scope)
        self.assertEqual(active, [])
        self.assertFalse(result.permitted)

    def test_the_superseded_event_remains_visible_in_history(self):
        """Not active is not deleted — the audit trail's entire value."""
        state = resolve("grant-sup", at=NOW, events=self.log)
        self.assertEqual([e.kind for e in state.history_events], ["granted", "superseded"])


class TestDocumentedRegrantMechanism(unittest.TestCase):
    """HOD-107: revoke-then-regrant-narrower resolves to the narrower scope.
    A re-grant is a NEW `granted` event — that is the documented mechanism."""

    def setUp(self):
        self.log = [
            evt("e1", "granted", BROAD, T0),
            evt("e2", "revoked", BROAD, T1),
            evt("e3", "granted", NARROW, T1 + timedelta(hours=1)),
        ]

    def test_regrant_resolves_active_at_the_narrower_scope(self):
        state = resolve("grant-sup", at=NOW, events=self.log)
        self.assertEqual(state.status, "active")
        self.assertEqual(state.active_scope.use_type, "fine_tuning")

    def test_folded_state_permits_the_narrower_but_not_the_broader_request(self):
        active = active_grant_events(self.log, at=NOW)
        self.assertEqual(len(active), 1)
        narrower = Scope(use_type="fine_tuning", model_class="open_weights",
                         commercial=False, territory=["US"], valid_from=NOW)
        broader = Scope(use_type="training", model_class="all_models",
                        commercial=True, territory=["WW"], valid_from=NOW)
        self.assertTrue(permits(active, narrower, at=NOW).permitted)
        self.assertFalse(permits(active, broader, at=NOW).permitted)

    def test_the_past_is_unchanged_by_the_regrant(self):
        before = resolve("grant-sup", at=T0 + timedelta(hours=1), events=self.log)
        self.assertEqual(before.status, "active")
        self.assertEqual(before.active_scope.use_type, "training")
        self.assertEqual(len(before.history_events), 1)


if __name__ == "__main__":
    unittest.main()
