"""
tests/test_revocation_reach.py — what a revocation reaches, stated as a test
(HOD-104, HOD-107, HOD-330).

This file exists to make the revocation cascade's reach a SPECIFIED property
rather than an emergent one, including where that reach falls short.

WHAT IT DOES. Revoking use type R terminates every active grant whose held use
type is in R's downward closure — R and everything R contains. Revoking
`training` therefore reaches `fine_tuning`, `rag_retrieval` and
`human_reference` grants, walked from the lattice's covering relation and never
enumerated in code. That is the documented behaviour and it is correct.

WHAT IT DOES NOT DO, AND WHY. It does not touch a grant held ABOVE R. Revoking
`fine_tuning` leaves a `training` grant standing, and a `training` grant permits
fine-tuning — so `permits(fine_tuning)` is still True afterwards. Six of the
twenty-five (held x revoked) pairs behave this way; `test_under_reach_matrix_is_exactly_six`
pins the count.

This is not a bug that can be fixed by inverting the walk. `Scope.use_type` holds
ONE value and the use types form a chain, so "training minus fine_tuning" is not
expressible: the only way to stop fine-tuning under a training grant is to
terminate the training grant entirely, destroying a permission the artist did not
revoke — irreversibly, because the log is append-only. Choosing that silently
would be worse than the current behaviour. The honest position is that partial
narrowing of a broader grant is OUT OF SCOPE and stated, in the README's
"What Hodi will not claim" and in docs/FINDINGS.md, rather than implied to work.

If that decision is ever revisited, these tests fail, which is the point.
"""

import unittest
from datetime import datetime, timezone
from typing import get_args

from src.resolve.evaluator import permits
from src.schema.grant_event import GrantEvent
from src.schema.lattice import USE_TYPE_CONTAINMENT
from src.schema.scope import Scope, UseType

AT = datetime(2026, 8, 1, tzinfo=timezone.utc)
USE_TYPES = sorted(get_args(UseType))


def scope(use_type: str) -> Scope:
    return Scope(use_type=use_type, model_class="all_models", commercial=True,
                 attribution_required=False, territory=[], valid_from=AT, valid_until=None)


def grant(use_type: str) -> GrantEvent:
    return GrantEvent(event_id="e", grant_id="g", work_id="w", counterparty_id="c",
                      scope=scope(use_type), kind="granted", issued_at=AT, signature="s")


def cascade_selects(held: str, revoked: str) -> bool:
    """The propagator's selection rule, read-only — see
    revocation_propagator.py::execute_revocation_cascade."""
    return held in USE_TYPE_CONTAINMENT.get(revoked, {revoked})


class RevocationReachTest(unittest.TestCase):

    def test_revoking_training_reaches_every_type_it_contains(self):
        """The documented cascade, and the one the demo and the video exercise."""
        for held in ("training", "fine_tuning", "rag_retrieval", "human_reference"):
            with self.subTest(held=held):
                self.assertTrue(cascade_selects(held, "training"),
                                f"revoking training must reach a {held} grant")

    def test_revoking_training_does_not_reach_synthesis(self):
        """`synthesis` is incomparable, not narrower — containment is a partial
        order, not a ranking."""
        self.assertFalse(cascade_selects("synthesis", "training"))
        self.assertFalse(cascade_selects("training", "synthesis"))

    def test_a_terminated_grant_stops_permitting(self):
        for held in ("training", "fine_tuning", "rag_retrieval", "human_reference"):
            with self.subTest(held=held):
                self.assertTrue(permits([grant(held)], scope(held)).permitted)

    def test_under_reach_matrix_is_exactly_six(self):
        """
        The stated limit, pinned. A pair is under-reached when the cascade
        selects nothing AND the surviving grant still permits the revoked type.

        If this count changes, either the lattice changed or the cascade's reach
        changed — both require updating the README disclosure and FINDINGS,
        which is exactly why the number is asserted rather than described.
        """
        under = [(h, r) for h in USE_TYPES for r in USE_TYPES
                 if not cascade_selects(h, r) and permits([grant(h)], scope(r)).permitted]
        self.assertEqual(
            sorted(under),
            sorted([("training", "fine_tuning"),
                    ("training", "rag_retrieval"),
                    ("training", "human_reference"),
                    ("fine_tuning", "rag_retrieval"),
                    ("fine_tuning", "human_reference"),
                    ("rag_retrieval", "human_reference")]),
            "the set of under-reached (held, revoked) pairs changed")
        self.assertEqual(len(under), 6)
        self.assertEqual(len(USE_TYPES) ** 2, 25)

    def test_every_under_reached_pair_is_a_strict_ancestor(self):
        """Characterises the limit rather than just counting it: the gap is
        exactly 'the held grant strictly contains the revoked type'."""
        for held in USE_TYPES:
            for revoked in USE_TYPES:
                if cascade_selects(held, revoked):
                    continue
                still_permitted = permits([grant(held)], scope(revoked)).permitted
                strictly_contains = (revoked in USE_TYPE_CONTAINMENT.get(held, set())
                                     and held != revoked)
                self.assertEqual(
                    still_permitted, strictly_contains,
                    f"held={held} revoked={revoked}: survival should hold exactly when the "
                    "held type strictly contains the revoked one")

    def test_the_gap_is_inexpressible_not_merely_unimplemented(self):
        """The reason the limit is stated rather than fixed: there is no use
        type meaning 'training but not fine_tuning', so no narrowing event could
        represent the correct outcome."""
        training_minus_fine_tuning = (USE_TYPE_CONTAINMENT["training"]
                                      - USE_TYPE_CONTAINMENT["fine_tuning"])
        self.assertEqual(training_minus_fine_tuning, {"training"})
        for candidate in USE_TYPES:
            self.assertNotEqual(
                USE_TYPE_CONTAINMENT.get(candidate, {candidate}), {"training"},
                f"{candidate!r} would express 'training without its descendants' — if such a "
                "use type now exists, the cascade CAN narrow and the limit should be fixed, "
                "not disclosed")


if __name__ == "__main__":
    unittest.main()
