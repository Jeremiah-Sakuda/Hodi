"""
Durable registry and Memory Bank (HOD-709, HOD-710).

The property under test, both halves: state read back by a FRESH instance
equals state written by a dead one. The registry and the Memory Bank each
claimed durability their mechanisms lacked — a Python dict rebuilt per
run. Both now fold over a pluggable append-only store; these tests prove
the fold against the in-memory twin (which shares the live store's
create-only collision semantics), and the HODI_E2E variants prove the
same fold against real Firestore with two separate clients.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone

from src.memory.event_store import InMemoryEventStore, DuplicateEventId
from src.memory.memory_bank import MemoryBank
from src.registry.registry import AgentRegistry, AgentPublication
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _pub(agent_id="negotiator-v1", role="licensing_negotiator") -> AgentPublication:
    return AgentPublication(
        agent_id=agent_id, name="Licensing Negotiator", version="1.0.0",
        owning_function=role, role=role, scopes=["grants"],
        service_account=f"{role}-sa@hodi-2026.iam.gserviceaccount.com",
        capabilities=["grants"],
    )


class TestMemoryBankSurvivesInstanceDeath(unittest.TestCase):
    def test_fresh_instance_folds_identical_state(self):
        """The HOD-331/HOD-710 acceptance property, now a property of the
        CLASS: the first instance dies (goes out of scope), a second instance
        over the same store re-hydrates the identical fold."""
        store = InMemoryEventStore()

        writer = MemoryBank(store=store)
        writer.append_event(GrantEvent(
            event_id="e1", grant_id="g1", work_id="w1", counterparty_id="c1",
            scope=Scope(use_type="training", valid_from=T0),
            kind="granted", issued_at=T0, signature="s"))
        writer.append_event(GrantEvent(
            event_id="e2", grant_id="g1", work_id="w1", counterparty_id="c1",
            scope=Scope(use_type="training", valid_from=T0),
            kind="revoked", issued_at=T0 + timedelta(days=1), signature="s"))
        state_before = writer.resolve_state("g1")
        del writer  # instance death

        reader = MemoryBank(store=store)
        state_after = reader.resolve_state("g1")
        self.assertEqual(state_after.status, "revoked")
        self.assertEqual(state_before.model_dump(), state_after.model_dump())

    def test_temporal_query_survives_rehydration(self):
        store = InMemoryEventStore()
        bank = MemoryBank(store=store)
        bank.append_event(GrantEvent(
            event_id="e1", grant_id="g1", work_id="w1", counterparty_id="c1",
            scope=Scope(use_type="training", valid_from=T0),
            kind="granted", issued_at=T0, signature="s"))
        bank.append_event(GrantEvent(
            event_id="e2", grant_id="g1", work_id="w1", counterparty_id="c1",
            scope=Scope(use_type="training", valid_from=T0),
            kind="revoked", issued_at=T0 + timedelta(days=2), signature="s"))

        fresh = MemoryBank(store=store)
        at_before = fresh.resolve_state("g1", at=T0 + timedelta(days=1))
        at_after = fresh.resolve_state("g1", at=T0 + timedelta(days=3))
        self.assertEqual(at_before.status, "active")
        self.assertEqual(at_after.status, "revoked")

    def test_append_only_discipline_is_enforced_by_the_store(self):
        bank = MemoryBank(store=InMemoryEventStore())
        ev = GrantEvent(
            event_id="e1", grant_id="g1", work_id="w1", counterparty_id="c1",
            scope=Scope(use_type="training", valid_from=T0),
            kind="granted", issued_at=T0, signature="s")
        bank.append_event(ev)
        with self.assertRaises(DuplicateEventId):
            bank.append_event(ev)


class TestRegistrySurvivesInstanceDeath(unittest.TestCase):
    def test_fresh_registry_folds_prior_publications(self):
        store = InMemoryEventStore()
        first = AgentRegistry(store=store)
        first.register(_pub())
        first.heartbeat("negotiator-v1")
        del first

        second = AgentRegistry(store=store)
        pubs = second.publications()
        self.assertIn("negotiator-v1", pubs)
        pub = pubs["negotiator-v1"]
        self.assertEqual(pub.status, "active")
        self.assertIsNotNone(pub.registered_at)
        self.assertIsNotNone(pub.last_heartbeat)
        self.assertEqual(pub.service_account,
                         "licensing_negotiator-sa@hodi-2026.iam.gserviceaccount.com")

    def test_deregistration_survives_and_history_is_kept(self):
        store = InMemoryEventStore()
        first = AgentRegistry(store=store)
        first.register(_pub())
        first.deregister("negotiator-v1", reason="quarantined_by_supervisor")
        del first

        second = AgentRegistry(store=store)
        self.assertFalse(second.is_registered("negotiator-v1"))
        history = second.publications(include_deregistered=True)
        self.assertEqual(history["negotiator-v1"].status, "deregistered")

    def test_discovery_does_not_disclose_deregistered_agents(self):
        registry = AgentRegistry()
        registry.register(_pub("propagator-v1", "revocation_propagator"))
        found = registry.discover("revocation_propagator", "rights_custodian")
        self.assertEqual(len(found), 1)
        registry.deregister("propagator-v1", reason="quarantined_by_supervisor")
        self.assertEqual(registry.discover("revocation_propagator", "rights_custodian"), [])

    def test_non_disclosure_for_unauthorized_roles_is_unchanged(self):
        registry = AgentRegistry()
        registry.register(_pub("propagator-v1", "revocation_propagator"))
        self.assertEqual(registry.discover("revocation_propagator", "licensing_negotiator"), [])

    def test_reregistration_after_deregistration_wins_the_fold(self):
        """A quarantined agent that is later redeployed re-registers; the fold
        resolves to the newest registration, with the full history intact."""
        registry = AgentRegistry()
        registry.register(_pub("propagator-v1", "revocation_propagator"))
        registry.deregister("propagator-v1", reason="quarantined_by_supervisor")
        newer = _pub("propagator-v1", "revocation_propagator").model_copy(update={"version": "1.0.1"})
        registry.register(newer)
        pubs = registry.publications()
        self.assertEqual(pubs["propagator-v1"].version, "1.0.1")
        self.assertEqual(pubs["propagator-v1"].status, "active")


@unittest.skipUnless(os.environ.get("HODI_E2E") == "1",
                     "Live-Firestore e2e test: set HODI_E2E=1 to run. It writes registry and "
                     "memory-bank events to real collections under test-prefixed ids.")
class TestDurableStateLive(unittest.TestCase):
    """The same fold, against real Firestore, with two separate clients —
    instance death crossed with process death (HOD-709/HOD-710 E2E)."""

    def test_registry_and_memory_bank_survive_across_clients(self):
        import uuid
        from src.memory.event_store import FirestoreEventStore

        suffix = uuid.uuid4().hex[:8]
        registry_a = AgentRegistry(store=FirestoreEventStore())
        agent_id = f"e2e-test-agent-{suffix}"
        registry_a.register(_pub(agent_id, "revocation_propagator"))

        registry_b = AgentRegistry(store=FirestoreEventStore())
        self.assertTrue(registry_b.is_registered(agent_id))

        bank_a = MemoryBank(store=FirestoreEventStore(), collection="e2e_memory_bank_events")
        gid = f"e2e-grant-{suffix}"
        bank_a.append_event(GrantEvent(
            event_id=f"e2e-{suffix}", grant_id=gid, work_id="w", counterparty_id="c",
            scope=Scope(use_type="training", valid_from=T0),
            kind="granted", issued_at=T0, signature="s"))
        bank_b = MemoryBank(store=FirestoreEventStore(), collection="e2e_memory_bank_events")
        self.assertEqual(bank_b.resolve_state(gid).status, "active")


if __name__ == "__main__":
    unittest.main()
