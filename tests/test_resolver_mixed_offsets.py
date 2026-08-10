"""
tests/test_resolver_mixed_offsets.py — the regression test for correction #8
(HOD-103, HOD-107).

`resolve()` folded events ordered by `issued_at.isoformat()` — the ISO *string*,
not the instant it denotes. For a log carrying mixed UTC offsets that is wrong,
because string comparison is lexicographic and time zones are not:

    granted at 2026-08-05T12:00:00+00:00  ->  12:00Z
    revoked at 2026-08-05T09:00:00-05:00  ->  14:00Z   (later!)

"09..." sorts before "12...", so the revocation folded in AHEAD of the grant it
revokes and the grant came out the other side alive.

The defect is fixed — the fold sorts on `issued_at.astimezone(timezone.utc)`.
This file exists because until now NOTHING TESTED IT. That is a live gap on the
project's flagship honesty claim: the blog leads with this defect, the demo's
byte-stability beat could never have caught it (the fold was deterministically
wrong, not unstable), and every truth-table fixture shares a single offset. A
fix with no test is a fix that survives at the mercy of the next refactor.

Each test below FAILS if the sort key reverts to `.isoformat()`.
"""

import unittest
from datetime import datetime, timedelta, timezone

from src.resolve.resolver import resolve, active_grant_events
from src.resolve.evaluator import permits
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope

WORK = "work-offsets-001"
GRANT = "grant-offsets-001"
CP = "counterparty-offsets"

# 12:00Z, then 14:00Z expressed as 09:00-05:00. The revocation is genuinely
# later; only its rendering sorts earlier.
GRANTED_AT = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
REVOKED_AT = datetime(2026, 8, 5, 9, 0, 0, tzinfo=timezone(timedelta(hours=-5)))


def scope(use_type: str = "training") -> Scope:
    return Scope(
        use_type=use_type, model_class="all_models", commercial=True,
        attribution_required=False, territory=[], valid_from=GRANTED_AT,
        valid_until=None,
    )


def event(kind: str, issued_at: datetime, event_id: str) -> GrantEvent:
    return GrantEvent(
        event_id=event_id, grant_id=GRANT, work_id=WORK, counterparty_id=CP,
        scope=scope(), kind=kind, issued_at=issued_at, signature=f"SIG_{kind.upper()}",
    )


class MixedOffsetFoldTest(unittest.TestCase):
    """The exact log shape from correction #8."""

    def setUp(self):
        self.events = [
            event("granted", GRANTED_AT, "evt-granted"),
            event("revoked", REVOKED_AT, "evt-revoked"),
        ]

    def test_the_offsets_really_do_sort_the_wrong_way_as_strings(self):
        """Guards the guard: if this stops holding, the fixture no longer
        reproduces the defect and the tests below become vacuous."""
        self.assertLess(REVOKED_AT.isoformat(), GRANTED_AT.isoformat(),
                        "fixture no longer exercises the string-sort defect")
        self.assertGreater(REVOKED_AT.astimezone(timezone.utc),
                           GRANTED_AT.astimezone(timezone.utc),
                           "fixture revocation must genuinely be the later instant")

    def test_resolve_reports_revoked(self):
        self.assertEqual(resolve(GRANT, events=self.events).status, "revoked")

    def test_resolve_returns_no_active_scope(self):
        self.assertIsNone(resolve(GRANT, events=self.events).active_scope)

    def test_active_grant_events_returns_nothing(self):
        self.assertEqual(active_grant_events(self.events), [])

    def test_permits_refuses_the_revoked_use_type(self):
        """The end of the chain, and the reason the defect mattered: permits()
        answered True for `training` on a grant that had been revoked."""
        self.assertFalse(permits(active_grant_events(self.events), scope("training")).permitted)

    def test_fold_is_order_independent(self):
        """Byte-stable replay still holds — the criterion was never wrong, only
        insufficient. Both orderings must now agree AND be correct."""
        forward = resolve(GRANT, events=self.events)
        reverse = resolve(GRANT, events=list(reversed(self.events)))
        self.assertEqual(forward.status, reverse.status)
        self.assertEqual(forward.status, "revoked")


class NaiveTimestampTest(unittest.TestCase):
    """A naive (tz-less) timestamp must not crash the fold or silently sort as
    though it were UTC-adjacent. Firestore normalises to UTC, but every
    JSON-sourced log — the committed fixture log and the failure-tolerance
    drill — takes the untrusted path."""

    def test_naive_and_aware_events_fold_without_error(self):
        events = [
            event("granted", datetime(2026, 8, 5, 12, 0, 0), "evt-granted-naive"),
            event("revoked", REVOKED_AT, "evt-revoked-aware"),
        ]
        state = resolve(GRANT, events=events)
        self.assertIn(state.status, {"revoked", "active"})
        self.assertEqual(state.status, resolve(GRANT, events=list(reversed(events))).status,
                         "a mixed naive/aware log must still fold order-independently")


class RegrantAcrossOffsetsTest(unittest.TestCase):
    """The documented re-grant mechanism, expressed across offsets: revoke, then
    a NEW granted event that supersedes. The later instant must win even when
    its rendering sorts earlier."""

    def test_regrant_at_a_later_instant_in_a_western_offset_wins(self):
        events = [
            event("granted", GRANTED_AT, "evt-1-granted"),
            event("revoked", datetime(2026, 8, 5, 13, 0, tzinfo=timezone.utc), "evt-2-revoked"),
            # 09:00-08:00 == 17:00Z, the latest instant, but sorts first as a string.
            event("granted", datetime(2026, 8, 5, 9, 0,
                                      tzinfo=timezone(timedelta(hours=-8))), "evt-3-regrant"),
        ]
        self.assertEqual(resolve(GRANT, events=events).status, "active")
        self.assertTrue(permits(active_grant_events(events), scope("training")).permitted)


if __name__ == "__main__":
    unittest.main()
