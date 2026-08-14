"""
Revocation idempotency and the notice outbox (HOD-708).

The property under test: retrying a failed revocation cannot double its
effects.

The cascade performs multiple effects per affected grant — terminate the
grant, record the notice obligation, deliver the notice. Before this
existed, every id was a fresh uuid4 and the effects were separate writes:
a crash between them followed by a retry duplicated notices, and nothing
could tell a retry from a new revocation. Now: the revoked event and the
outbox record commit atomically under operation-derived deterministic ids,
delivery is a separate retryable phase whose discharge marker is the notice
document itself, and a replay collides on create() instead of duplicating.

Everything runs offline against the gateway's write sink, which raises on
duplicate ids exactly as live Firestore `.create()` does — an offline path
that cannot collide would make these tests tests of nothing.
"""

import os
import unittest
from datetime import datetime, timezone

from src.gateway.gateway import AgentGateway, DocumentAlreadyExists
from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope
from src.schema.revocation import revocation_effect_id
from src.schema.iam_policy import AGENT_SA_MAP

PROPAGATOR_SA = AGENT_SA_MAP["revocation_propagator"]["sa_email"]
T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _granted(grant_id, work_id="work-essay-001", counterparty="acme-intelligence-labs",
             use_type="training") -> dict:
    return GrantEvent(
        event_id=f"evt-{grant_id}", grant_id=grant_id, work_id=work_id,
        counterparty_id=counterparty,
        scope=Scope(use_type=use_type, valid_from=T0),
        kind="granted", issued_at=T0, signature="s",
    ).model_dump(mode="json")


class TestRevocationIdempotency(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.gateway = AgentGateway(offline_reads={"grants": [_granted("g-1")]})
        self.propagator = RevocationPropagatorAgent(gateway=self.gateway)

    def _count(self, collection):
        return len(self.gateway._offline_writes.get(collection, {}))

    def test_single_run_commits_one_event_one_outbox_one_notice(self):
        result = self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-test-1")
        self.assertEqual(len(result.affected_grants), 1)
        self.assertEqual(len(result.issued_notices), 1)
        self.assertEqual(result.replayed_effects, 0)
        self.assertEqual(self._count("grants"), 1)             # the revoked event
        self.assertEqual(self._count("revocation_outbox"), 1)
        self.assertEqual(self._count("revocation_notices"), 1)

    def test_full_retry_with_same_operation_id_doubles_nothing(self):
        first = self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-retry")
        second = self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-retry")
        self.assertEqual(self._count("grants"), 1)
        self.assertEqual(self._count("revocation_outbox"), 1)
        self.assertEqual(self._count("revocation_notices"), 1)
        self.assertGreaterEqual(second.replayed_effects, 0)
        # The retry returns the SAME receipt identity, not a second receipt.
        self.assertEqual(first.issued_notices[0].revocation_id,
                         second.issued_notices[0].revocation_id)

    def test_crash_between_terminate_and_delivery_then_retry_yields_exactly_one_notice(self):
        """The review's exact scenario: notice-owed committed, delivery fails,
        retry occurs. The retry must discharge the obligation once — never
        issue a second notice, never duplicate the revocation event."""
        real_write = self.gateway.write_document
        crashed = {}

        def crash_on_first_notice(calling_sa, calling_role_key, target_collection, doc_id, data, lease_id=None):
            if target_collection == "revocation_notices" and not crashed:
                crashed["yes"] = True
                raise ConnectionError("simulated network failure during delivery")
            return real_write(calling_sa, calling_role_key, target_collection, doc_id, data, lease_id=lease_id)

        self.gateway.write_document = crash_on_first_notice
        with self.assertRaises(ConnectionError):
            self.propagator.execute_revocation_cascade(
                "work-essay-001", "training", operation_id="op-crash")

        # Phase 1 committed atomically; delivery did not happen.
        self.assertEqual(self._count("grants"), 1)
        self.assertEqual(self._count("revocation_outbox"), 1)
        self.assertEqual(self._count("revocation_notices"), 0)

        self.gateway.write_document = real_write
        result = self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-crash")
        self.assertEqual(self._count("grants"), 1, "retry duplicated the revocation event")
        self.assertEqual(self._count("revocation_notices"), 1, "retry did not deliver exactly one notice")
        self.assertEqual(result.replayed_effects, 1)
        self.assertEqual(len(result.issued_notices), 1)

    def test_delivery_alone_is_replayable(self):
        self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-deliver")
        receipts_again = self.propagator.deliver_pending_notices(operation_id="op-deliver")
        self.assertEqual(len(receipts_again), 1)
        self.assertEqual(self._count("revocation_notices"), 1)

    def test_new_operation_after_completion_affects_nothing(self):
        """A DIFFERENT operation_id is a new operation — and the fold protects
        it: the grant is already revoked, no longer active, not affected."""
        self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-a")
        result_b = self.propagator.execute_revocation_cascade(
            "work-essay-001", "training", operation_id="op-b")
        self.assertEqual(len(result_b.affected_grants), 0)
        self.assertEqual(self._count("grants"), 1)
        self.assertEqual(self._count("revocation_notices"), 1)

    def test_effect_ids_are_deterministic_and_distinct(self):
        a = revocation_effect_id("op", "g", "revoked_event")
        self.assertEqual(a, revocation_effect_id("op", "g", "revoked_event"))
        self.assertNotEqual(a, revocation_effect_id("op", "g", "outbox"))
        self.assertNotEqual(a, revocation_effect_id("op", "g2", "revoked_event"))
        self.assertNotEqual(a, revocation_effect_id("op2", "g", "revoked_event"))


class TestGatewayAtomicityAndCollisionSemantics(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.gateway = AgentGateway()

    def test_offline_duplicate_create_raises_like_live(self):
        self.gateway.write_document(PROPAGATOR_SA, "revocation_propagator",
                                    "grants", "same-id", {"a": 1})
        with self.assertRaises(DocumentAlreadyExists):
            self.gateway.write_document(PROPAGATOR_SA, "revocation_propagator",
                                        "grants", "same-id", {"a": 2})
        # Append-only: the collision did not overwrite.
        self.assertEqual(self.gateway._offline_writes["grants"]["same-id"], {"a": 1})

    def test_atomic_batch_is_all_or_nothing(self):
        self.gateway.write_document(PROPAGATOR_SA, "revocation_propagator",
                                    "revocation_outbox", "occupied", {"x": 1})
        with self.assertRaises(DocumentAlreadyExists):
            self.gateway.write_documents_atomic(
                PROPAGATOR_SA, "revocation_propagator",
                writes=[("grants", "fresh-id", {"y": 1}),
                        ("revocation_outbox", "occupied", {"x": 2})])
        self.assertNotIn("fresh-id", self.gateway._offline_writes.get("grants", {}),
                         "a failed batch left a partial write behind")

    def test_atomic_batch_enforces_policy_on_every_collection(self):
        from src.gateway.gateway import GatewayPolicyDenial
        with self.assertRaises(GatewayPolicyDenial):
            self.gateway.write_documents_atomic(
                PROPAGATOR_SA, "revocation_propagator",
                writes=[("grants", "id-1", {}),
                        ("artists", "id-2", {})])  # propagator may not touch identity
        self.assertNotIn("id-1", self.gateway._offline_writes.get("grants", {}),
                         "a policy-denied batch still wrote its permitted half")

    def test_reads_see_writes_offline(self):
        self.gateway.write_document(PROPAGATOR_SA, "revocation_propagator",
                                    "grants", "id-1", {"grant_id": "g", "k": "v"})
        rows = self.gateway.read_collection(PROPAGATOR_SA, "revocation_propagator",
                                            "grants", filters={"grant_id": "g"})
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
