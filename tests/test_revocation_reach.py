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
from datetime import datetime, timezone
from typing import get_args

from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.gateway.gateway import AgentGateway
from src.resolve.evaluator import permits
from src.schema.grant_event import GrantEvent
from src.schema.lattice import USE_TYPE_CONTAINMENT
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
