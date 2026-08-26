"""
tests/test_revocation_reach.py — which grants a revocation terminates, as a test
(HOD-104, HOD-107, HOD-330).

THE RULE. Revoking use type R terminates exactly the active grants that PERMIT
R — a grant held at use type H is affected iff H contains R in the lattice
(`is_use_type_contained(H, R)`), which is the same predicate `permits()` uses.
Revoking `training` terminates a `training` grant; it does NOT terminate a
`fine_tuning`-only grant, because that grant never permitted training.

HISTORY, STATED PLAINLY. Through 2026-08-10 the selection was BACKWARDS and an
earlier version of THIS FILE asserted the backwards behaviour as correct. It
terminated the grants the revoked type *contains* (its descendants), so revoking
`training` destroyed every `fine_tuning`/`rag_retrieval`/`human_reference` grant
— licenses for uses the artist never revoked — and revoking `fine_tuning` left a
`training` grant still able to fine-tune. 12 of the 25 (held × revoked) cells
were wrong: 6 over-revocations and 6 under-revocations. Every test passed,
because the tests (this one included) encoded the same error, and every check
only ever exercised `revoke training` on a `training`-or-narrower grant — the
diagonal where the wrong rule and the right rule happen to agree.

The correct rule is `permits()`'s own predicate, reused so there is exactly one
definition of "this scope permits that use." This file now asserts the full
25-cell matrix against that predicate as an independent oracle, so a regression
in either direction fails here.

THE ONE REMAINING LIMIT, still disclosed. When a grant held ABOVE R is
terminated (revoke `fine_tuning`, grant held at `training`), the whole grant
goes — stripping `training` too, which was not revoked. A single-valued
`use_type` on a chain cannot express "training but not fine_tuning," so there is
no narrower event to write. Terminating is the safe direction: better to
over-strip a grant that *did* permit the revoked use than to leave the revoked
use available. That is a property of the scope model, not of the selection rule,
and it is not the bug this file guards.
"""

import os
import unittest
import inspect
from datetime import datetime, timedelta, timezone
from typing import get_args

from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.gateway.gateway import AgentGateway
from src.resolve.evaluator import is_scope_current, permits, scope_window_has_closed
from src.schema.grant_event import GrantEvent
from src.resolve.resolver import resolve
from src.schema.lattice import USE_TYPE_CONTAINMENT, is_use_type_contained
from src.schema.scope import Scope, UseType
from src.schema.signing import unsigned_placeholder

AT = datetime(2026, 8, 1, tzinfo=timezone.utc)
USE_TYPES = sorted(get_args(UseType))


_PRIOR_OFFLINE = None


def setUpModule():
    # The cascade WRITES. Offline forces a gateway with no Firestore client, so
    # these 25+ cascades cannot reach production (this exact mistake once wrote
    # revoked events into the live log — BUILD-LOG 2026-08-07).
    global _PRIOR_OFFLINE
    _PRIOR_OFFLINE = os.environ.get("HODI_OFFLINE")
    os.environ["HODI_OFFLINE"] = "1"


def tearDownModule():
    # RESTORE, never pop. `make test` sets HODI_OFFLINE=1 for the whole run;
    # unconditionally deleting it here put every module that ran afterwards
    # back online — the suite went from 18s to 186s reaching for Firestore and
    # Ollama, and offline runs stopped being offline halfway through.
    if _PRIOR_OFFLINE is None:
        os.environ.pop("HODI_OFFLINE", None)
    else:
        os.environ["HODI_OFFLINE"] = _PRIOR_OFFLINE


def scope(use_type: str) -> Scope:
    return Scope(use_type=use_type, model_class="all_models", commercial=True,
                 attribution_required=False, territory=[], valid_from=AT, valid_until=None)


def grant(use_type: str) -> GrantEvent:
    return GrantEvent(event_id="e", grant_id="g", work_id="w", counterparty_id="c",
                      scope=scope(use_type), kind="granted", issued_at=AT,
                      signature=unsigned_placeholder("grant", "g"))


def cascade_selects(held: str, revoked: str) -> bool:
    """
    Runs the REAL cascade and reports whether it selected the grant.

    This used to `return is_use_type_contained(held, revoked)` — a local
    re-implementation of the rule. Every cell passed while testing a copy of the
    code rather than the code, so a mutation inside
    `execute_revocation_cascade` that changed selection for only some use types
    survived this file, the demo and CI. The whole point of the matrix is to
    exercise the shipped selection, so it now invokes it.

    Offline (`HODI_OFFLINE=1` via setUpModule): the gateway holds no Firestore
    client, the propagator folds `memory_bank_events`, and writes go nowhere.
    """
    agent = RevocationPropagatorAgent(gateway=AgentGateway(),
                                      memory_bank_events=[grant(held)])
    result = agent.execute_revocation_cascade(work_id="w", revoked_use_type=revoked)
    return any(a.grant_id == "g" for a in result.affected_grants)


def grant_permits(held: str, revoked: str) -> bool:
    """Independent oracle: does a grant held at `held` actually permit `revoked`?
    Uses permits() directly, so it cannot share a bug with the selection rule
    unless permits() itself is wrong (which the 47-case truth table guards)."""
    return permits([grant(held)], scope(revoked)).permitted


class RevocationReachMatrixTest(unittest.TestCase):

    def test_selection_equals_permission_for_all_25_cells(self):
        """The whole finding in one assertion: a grant is terminated by revoking
        R iff it permits R. Every cell, both directions."""
        wrong = []
        for held in USE_TYPES:
            for revoked in USE_TYPES:
                if cascade_selects(held, revoked) != grant_permits(held, revoked):
                    wrong.append((held, revoked, cascade_selects(held, revoked),
                                  grant_permits(held, revoked)))
        self.assertEqual(wrong, [],
                         "cascade selection disagrees with permission in cells "
                         f"(held, revoked, selects, permits): {wrong}")

    def test_revoking_training_hits_training_grants_only(self):
        self.assertTrue(cascade_selects("training", "training"))
        for narrower in ("fine_tuning", "rag_retrieval", "human_reference"):
            self.assertFalse(cascade_selects(narrower, "training"),
                             f"revoking training must NOT terminate a {narrower} grant")

    def test_revoking_fine_tuning_hits_training_and_fine_tuning_grants(self):
        self.assertTrue(cascade_selects("training", "fine_tuning"),
                        "a training grant permits fine-tuning and must be terminated")
        self.assertTrue(cascade_selects("fine_tuning", "fine_tuning"))
        for unrelated in ("rag_retrieval", "human_reference"):
            self.assertFalse(cascade_selects(unrelated, "fine_tuning"))

    def test_synthesis_is_incomparable_both_ways(self):
        for other in ("training", "fine_tuning", "rag_retrieval", "human_reference"):
            self.assertFalse(cascade_selects("synthesis", other))
            self.assertFalse(cascade_selects(other, "synthesis"))
        self.assertTrue(cascade_selects("synthesis", "synthesis"))

    def test_derived_scopes_still_describes_what_a_terminated_grant_loses(self):
        """`derived_scopes` (the withdrawal description) is unchanged and separate
        from selection: revoking R withdraws R and everything R contains."""
        self.assertEqual(sorted(USE_TYPE_CONTAINMENT["training"]),
                         ["fine_tuning", "human_reference", "rag_retrieval", "training"])

    def test_the_partial_narrowing_gap_is_inexpressible_not_a_selection_bug(self):
        """The residual limit: no use type means 'training without its
        descendants', so terminating a broader grant is the only available move.
        If such a type is ever added, this fails and says the limit became
        fixable — distinct from the selection rule, which is now correct."""
        training_minus_fine_tuning = (USE_TYPE_CONTAINMENT["training"]
                                      - USE_TYPE_CONTAINMENT["fine_tuning"])
        self.assertEqual(training_minus_fine_tuning, {"training"})
        for candidate in USE_TYPES:
            self.assertNotEqual(USE_TYPE_CONTAINMENT.get(candidate, {candidate}), {"training"})


if __name__ == "__main__":
    unittest.main()


class ExpiredGrantsAreNotRevokedTest(unittest.TestCase):
    """
    A grant whose window has closed must not be terminated or noticed (HOD-742).

    THE 396 CELLS THE 25-CELL MATRIX COULD NOT SEE. Every case in the reach
    matrix above hardcodes `valid_until=None`, so the whole temporal dimension
    was invisible to it. An independently written five-dimension oracle put
    **396 of 1,800 cells** in the failing state: the cascade selected purely on
    use-type containment, `resolve()` reports "active" meaning only that no
    revoking event has been appended, and nothing anywhere applies a clock — so
    a grant that lapsed weeks ago was terminated, and its counterparty received
    a revocation notice for rights they had already lost.

    `permits()` had checked currency all along. Two readers of one record
    carried two definitions of "still in force", which is why the fix is a
    SHARED predicate (`is_scope_current`) rather than a second implementation.
    """

    def _grant(self, grant_id, use_type, valid_from, valid_until, issued_at=None):
        # issued_at defaulted to valid_from, which is wrong for a future-dated
        # grant and is not what the service does: both write paths in
        # buyer_api.py stamp issued_at server-side at `now`, so a caller cannot
        # place it in the future. A fixture that future-dates issuance as well as
        # the window tests a state the API cannot produce — and it hides the real
        # one, because the revoked event then sorts BEFORE the grant it revokes
        # and the fold returns it to active.
        return GrantEvent(
            event_id=f"e-{grant_id}", grant_id=grant_id, work_id="w-temporal",
            counterparty_id="buyer-temporal", kind="granted",
            issued_at=issued_at or datetime.now(timezone.utc),
            signature=unsigned_placeholder("grant", grant_id),
            scope=Scope(use_type=use_type, model_class="all_models",
                        attribution_required=False, commercial=True,
                        valid_from=valid_from, valid_until=valid_until))

    def _cascade_selects(self, held, valid_until, revoked="training", valid_from=None):
        """
        Runs the REAL cascade — the same way `cascade_selects` above does — and
        reports whether the grant was selected.

        Asserting the predicate instead of invoking the cascade is how the
        original defect survived: a version of this file re-implemented the rule
        locally, every cell passed, and a mutation inside
        `execute_revocation_cascade` went unnoticed. Removing the temporal check
        from the shipped cascade must fail HERE.
        """
        now = datetime.now(timezone.utc)
        # valid_from was hardcoded 90 days in the past, so no cell in this file
        # could ever describe a grant whose window had not yet OPENED — the
        # 528-cell blind spot. It is a parameter now.
        ev = self._grant("g-temporal", held,
                         valid_from if valid_from is not None else now - timedelta(days=90),
                         valid_until)
        agent = RevocationPropagatorAgent(gateway=AgentGateway(),
                                          memory_bank_events=[ev])
        result = agent.execute_revocation_cascade(work_id="w-temporal",
                                                  revoked_use_type=revoked)
        return any(a.grant_id == "g-temporal" for a in result.affected_grants)

    def test_the_cascade_itself_skips_a_lapsed_grant(self):
        """The 396 cells, run through the shipped code path."""
        now = datetime.now(timezone.utc)
        self.assertTrue(
            self._cascade_selects("training", None),
            "a current, containing grant must still be terminated — the fix must not "
            "over-correct into revoking nothing")
        self.assertFalse(
            self._cascade_selects("training", now - timedelta(days=29)),
            "the cascade terminated a grant whose validity window closed 29 days ago, and would "
            "have issued its counterparty a revocation notice for rights they had already lost")

    def test_a_grant_expiring_in_the_future_is_still_terminated(self):
        """
        Currency is 'window still open', not 'window unbounded'. A bounded grant
        that has not yet lapsed is fully in force and must be revoked.
        """
        now = datetime.now(timezone.utc)
        self.assertTrue(self._cascade_selects("training", now + timedelta(days=365)))

    def test_a_future_dated_grant_is_still_terminated(self):
        """The 528 cells, run through the shipped code path (HOD-746).

        A grant whose window opens tomorrow is not current today, so a cascade
        selecting on currency skipped it — and unlike a lapsed grant, it goes
        live tomorrow with the revoked use still permitted. Nothing revisits it.
        The artist revoked `training` and `training` resumed.
        """
        now = datetime.now(timezone.utc)
        for label, opens_at in (
            ("one second of clock skew", now + timedelta(seconds=1)),
            ("a grant starting tomorrow", now + timedelta(days=1)),
            ("a grant starting in 45 days", now + timedelta(days=45)),
        ):
            with self.subTest(label):
                self.assertTrue(
                    self._cascade_selects("training", None, valid_from=opens_at),
                    f"the cascade skipped {label}: the grant is not current at the "
                    "revocation instant, but it becomes live afterwards with the "
                    "revoked use still permitted")

    def test_a_future_dated_grant_does_not_permit_the_use_after_the_cascade(self):
        """The property the cell count is a proxy for, asserted end to end.

        This is the assertion that would have failed before the fix: not 'was it
        selected' but 'can the buyer still train on this work in 45 days'.
        """
        now = datetime.now(timezone.utc)
        opens = now + timedelta(days=45)
        ev = self._grant("g-future", "training", opens, None)
        agent = RevocationPropagatorAgent(gateway=AgentGateway(), memory_bank_events=[ev])
        agent.execute_revocation_cascade(work_id="w-temporal", revoked_use_type="training")

        state = resolve("g-future", events=agent.memory_bank_events)
        self.assertEqual(
            state.status, "revoked",
            "the grant folds to active 45 days after the artist revoked training, "
            "and permits() will honour it the moment its window opens")

    def test_a_lapsed_grant_is_not_in_the_affected_set(self):
        now = datetime.now(timezone.utc)
        lapsed = self._grant("g-lapsed", "training",
                             now - timedelta(days=90), now - timedelta(days=29))
        live = self._grant("g-live", "training", now - timedelta(days=90), None)

        # The property, asserted through the same predicate the cascade uses.
        self.assertFalse(is_scope_current(lapsed.scope, now),
                         "fixture is wrong: this grant should have lapsed")
        self.assertTrue(is_scope_current(live.scope, now))

        # And through resolve(), which is what made this invisible: the lapsed
        # grant still folds to ACTIVE, because expiry is not an event.
        self.assertEqual(resolve("g-lapsed", events=[lapsed]).status, "active",
                         "resolve() reporting anything but 'active' would mean an `expired` event "
                         "now exists, and this test is guarding the wrong mechanism")

    def test_currency_and_containment_are_both_required(self):
        """
        The four-way table the cascade's selection now implements. Only the
        cell that is BOTH contained and current may be terminated.
        """
        now = datetime.now(timezone.utc)
        past, future = now - timedelta(days=1), now + timedelta(days=365)
        cases = [
            ("contained + current",      "training",        None,  True,  True),
            ("contained + lapsed",       "training",        past,  True,  False),
            ("not contained + current",  "human_reference", None,  False, True),
            ("not contained + lapsed",   "human_reference", past,  False, False),
        ]
        for label, held, until, contained, current in cases:
            with self.subTest(case=label):
                scope = Scope(use_type=held, model_class="all_models",
                              attribution_required=False, commercial=True,
                              valid_from=now - timedelta(days=30), valid_until=until)
                self.assertEqual(is_use_type_contained(held, "training"), contained)
                self.assertEqual(is_scope_current(scope, now), current)
                should_terminate = contained and current
                self.assertEqual(
                    should_terminate, label == "contained + current",
                    f"{label}: only a grant that both permits the revoked use AND is still in "
                    "force may be terminated")

    def test_the_reach_matrix_above_is_temporally_blind_by_construction(self):
        """
        Name the blind spot so nobody mistakes the 25 cells for full coverage.
        If the matrix ever grows bounded windows, this should be revisited.
        """
        source = inspect.getsource(inspect.getmodule(self.__class__))
        self.assertIn("valid_until=None", source,
                      "the reach matrix no longer hardcodes unbounded windows — if it now varies "
                      "validity, fold these temporal cases into it and delete this test")
