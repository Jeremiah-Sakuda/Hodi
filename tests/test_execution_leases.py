"""
Execution leases (HOD-707).

The property under test: an abandoned worker cannot commit after quarantine.

Python cannot kill a thread, so "quarantined" used to mean "no new work is
routed to it" — the abandoned thread kept running, and a late wake-up could
still write. The lease closes that: the supervisor revokes the lease at the
moment of abandonment, and the GATEWAY checks lease validity immediately
before every supervised write. The worker's cooperation is not part of the
guarantee — which is why the hung-worker test below uses a REAL blocked
thread and a REAL supervisor, never a mock of either.
"""

import os
import time
import threading
import unittest
from datetime import datetime, timedelta, timezone

from src.supervisor.lease import LeaseLedger
from src.supervisor.supervisor import Supervisor
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial

PROPAGATOR_SA = "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com"


def _write(gateway, lease_id, doc_id="d1"):
    gateway.write_document(
        calling_sa=PROPAGATOR_SA, calling_role_key="revocation_propagator",
        target_collection="grants", doc_id=doc_id,
        data={"k": "v"}, lease_id=lease_id)


class TestLeaseLedgerFold(unittest.TestCase):
    def setUp(self):
        self.ledger = LeaseLedger()

    def test_issued_lease_is_active(self):
        lease = self.ledger.issue("agent-a", "task-1", ttl_seconds=60)
        self.assertTrue(self.ledger.is_valid(lease))
        self.assertEqual(self.ledger.state(lease).status, "active")

    def test_revoked_lease_is_invalid_and_keeps_its_reason(self):
        lease = self.ledger.issue("agent-a", "task-1", ttl_seconds=60)
        self.ledger.revoke(lease, reason="deadline_exceeded")
        state = self.ledger.state(lease)
        self.assertEqual(state.status, "revoked")
        self.assertIn("deadline_exceeded", state.revoked_reason)
        self.assertFalse(self.ledger.is_valid(lease))

    def test_released_lease_cannot_be_reused(self):
        lease = self.ledger.issue("agent-a", "task-1", ttl_seconds=60)
        self.ledger.release(lease)
        self.assertFalse(self.ledger.is_valid(lease))

    def test_expired_ttl_invalidates_even_without_revocation(self):
        """The TTL is the backstop for a DEAD supervisor whose revoke never
        ran. An unrevoked lease past its expiry is invalid on the fold."""
        lease = self.ledger.issue("agent-a", "task-1", ttl_seconds=60)
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        self.assertFalse(self.ledger.is_valid(lease, at=future))
        self.assertEqual(self.ledger.state(lease, at=future).status, "expired")

    def test_ledger_is_append_only(self):
        """Revocation is a new event; the issuance event survives it."""
        lease = self.ledger.issue("agent-a", "task-1", ttl_seconds=60)
        self.ledger.revoke(lease, reason="r")
        kinds = [e.kind for e in self.ledger.events_for(lease)]
        self.assertEqual(kinds, ["issued", "revoked"])

    def test_unknown_lease_is_invalid(self):
        self.assertFalse(self.ledger.is_valid("lease-never-issued"))
        self.assertFalse(self.ledger.is_valid(None))


class TestGatewayLeaseEnforcement(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.ledger = LeaseLedger()
        self.gateway = AgentGateway(lease_ledger=self.ledger)

    def test_valid_lease_permits_the_write(self):
        lease = self.ledger.issue("propagator", "task-1", ttl_seconds=60)
        _write(self.gateway, lease)  # must not raise

    def test_revoked_lease_write_is_a_structured_denial(self):
        lease = self.ledger.issue("propagator", "task-1", ttl_seconds=60)
        self.ledger.revoke(lease, reason="deadline_exceeded (0.2s) for agent 'propagator'")
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            _write(self.gateway, lease)
        denial = ctx.exception.denial
        self.assertEqual(denial.policy_consulted, "execution_lease_v1")
        self.assertEqual(denial.outcome, "DENIED")
        self.assertIn("stale execution lease", denial.reason)
        self.assertEqual(len(self.gateway.denial_events), 1)

    def test_missing_lease_in_supervised_context_is_denied_not_grandfathered(self):
        """Fail closed: with a ledger attached, no-lease is a violation — the
        same shape as a missing session context on reads."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            _write(self.gateway, lease_id=None)
        self.assertEqual(ctx.exception.denial.policy_consulted, "execution_lease_v1")
        self.assertIn("NO execution lease", ctx.exception.denial.reason)

    def test_unsupervised_gateway_is_unchanged(self):
        """Without a ledger the gateway behaves exactly as before — the direct
        API path is not silently broken by the lease feature."""
        gateway = AgentGateway()  # no ledger
        _write(gateway, lease_id=None)  # must not raise

    def test_policy_denial_still_wins_over_lease_check(self):
        """Collection policy is consulted FIRST: a role that may not touch the
        collection is refused for THAT reason, lease or no lease."""
        lease = self.ledger.issue("propagator", "task-1", ttl_seconds=60)
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.gateway.write_document(
                calling_sa=PROPAGATOR_SA, calling_role_key="revocation_propagator",
                target_collection="artists", doc_id="d", data={}, lease_id=lease)
        self.assertEqual(ctx.exception.denial.policy_consulted, "gateway_policy_v1")


class TestAbandonedWorkerCannotCommit(unittest.TestCase):
    """The acceptance criterion, with a REAL hung worker (HOD-707)."""

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

    def test_woken_worker_write_is_refused_and_standby_result_stands(self):
        ledger = LeaseLedger()
        gateway = AgentGateway(lease_ledger=ledger)
        supervisor = Supervisor(deadline_seconds=0.2, lease_ledger=ledger)

        release_the_worker = threading.Event()
        worker_outcome = {}
        worker_finished = threading.Event()

        def hung_worker(lease_id=None):
            # Simulates a stalled dependency: blocks past its deadline WHILE
            # HOLDING ITS LEASE, then wakes and tries to commit.
            release_the_worker.wait(timeout=10)
            try:
                _write(gateway, lease_id, doc_id="late-write")
                worker_outcome["committed"] = True
            except GatewayPolicyDenial as e:
                worker_outcome["denial"] = e.denial
            finally:
                worker_finished.set()

        # 1. The supervisor abandons the task at its deadline...
        with self.assertRaises(TimeoutError):
            supervisor.execute_bounded_task("propagator-hung", hung_worker)
        self.assertEqual(supervisor.abandoned_events[-1].reason, "deadline_exceeded")
        self.assertEqual(supervisor.abandoned_events[-1].written_by, "supervisor")

        # 2. ...the standby completes meanwhile, under its own valid lease...
        def standby(lease_id=None):
            _write(gateway, lease_id, doc_id="standby-write")
            return {"status": "completed_degraded"}

        result = supervisor.execute_bounded_task("propagator-standby", standby)
        self.assertEqual(result["status"], "completed_degraded")

        # 3. ...and when the abandoned worker finally wakes, its commit is
        # refused at the gateway as a structured stale-lease denial. The
        # worker was NEVER asked to cooperate: it runs the same write call
        # the healthy path runs.
        release_the_worker.set()
        self.assertTrue(worker_finished.wait(timeout=10))
        self.assertNotIn("committed", worker_outcome,
                         "an abandoned worker committed after quarantine — the lease did not fence it")
        denial = worker_outcome["denial"]
        self.assertEqual(denial.policy_consulted, "execution_lease_v1")
        self.assertIn("stale execution lease", denial.reason)

    def test_successful_task_releases_its_lease(self):
        ledger = LeaseLedger()
        gateway = AgentGateway(lease_ledger=ledger)
        supervisor = Supervisor(deadline_seconds=5.0, lease_ledger=ledger)
        seen = {}

        def worker(lease_id=None):
            seen["lease"] = lease_id
            _write(gateway, lease_id)
            return "ok"

        self.assertEqual(supervisor.execute_bounded_task("propagator", worker), "ok")
        self.assertEqual(ledger.state(seen["lease"]).status, "released",
                         "a finished task's lease must not remain replayable")

    def test_lease_is_revoked_before_abandonment_surfaces(self):
        """Ordering: by the time the caller learns of the timeout, the ledger
        already refuses the lease — there is no window in which the fleet has
        rerouted but the old lease still commits."""
        ledger = LeaseLedger()
        supervisor = Supervisor(deadline_seconds=0.1, lease_ledger=ledger)
        captured = {}

        def worker(lease_id=None):
            captured["lease"] = lease_id
            time.sleep(5)

        with self.assertRaises(TimeoutError):
            supervisor.execute_bounded_task("propagator", worker)
        self.assertEqual(ledger.state(captured["lease"]).status, "revoked")


if __name__ == "__main__":
    unittest.main()
