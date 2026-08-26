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

import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from src.resolve.resolver import resolve, active_grant_events
from src.resolve.evaluator import permits
from pydantic import ValidationError
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
    """A naive (tz-less) timestamp is refused at the boundary (HOD-747).

    THIS TEST USED TO ACCEPT THE BUG. It was titled "must not ... silently sort
    as though it were UTC-adjacent" and then asserted
    `assertIn(status, {"revoked", "active"})` — the complete set of answers the
    fold can return. Both were passing grades, so the oracle restated the
    docstring and verified nothing, and the defect it was written to catch sat
    underneath it. Measured before the fix, on one identical event log:

        TZ=America/Los_Angeles -> active     (the buyer may train)
        TZ=UTC                 -> revoked    (the buyer may not)

    That is the project's signature defect — an operation that silently succeeds
    on input it cannot interpret — returning through the door the earlier fix
    left open. `resolve()` sorts on `.astimezone(timezone.utc)`, which does not
    raise on a naive datetime; it assumes server-local time.

    A test that admits both answers cannot fail. Each test below asserts exactly
    one.
    """

    NAIVE = datetime(2026, 8, 5, 12, 0, 0)

    def test_a_naive_timestamp_is_refused_rather_than_interpreted(self):
        with self.assertRaises(ValidationError) as caught:
            event("granted", self.NAIVE, "evt-granted-naive")
        self.assertIn("no UTC offset", str(caught.exception))

    def test_a_naive_window_bound_is_refused(self):
        """Same rule on the Scope, because `is_scope_current` reads it."""
        with self.assertRaises(ValidationError):
            Scope(use_type="training", model_class="all_models",
                  attribution_required=False, commercial=True, valid_from=self.NAIVE)

    def test_the_offset_aware_form_of_the_same_log_folds_identically_everywhere(self):
        """The property the rejected input made impossible, now assertable.

        Runs the fold under three server timezones. Before the fix this log —
        with the naive timestamp — returned two different answers. With offsets
        attached it must return exactly one, whatever the machine's clock says.
        """
        events = [
            event("granted", self.NAIVE.replace(tzinfo=timezone.utc), "evt-granted"),
            event("revoked", REVOKED_AT, "evt-revoked-aware"),
        ]
        answers = set()
        original = os.environ.get("TZ")
        try:
            for tz_name in ("America/Los_Angeles", "UTC", "Asia/Tokyo"):
                os.environ["TZ"] = tz_name
                time.tzset()
                answers.add(resolve(GRANT, events=events).status)
                answers.add(resolve(GRANT, events=list(reversed(events))).status)
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()

        self.assertEqual(
            answers, {"revoked"},
            f"the same log folded to {sorted(answers)} across server timezones; "
            "an authorization answer must not depend on where the process runs")


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
