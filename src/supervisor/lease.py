"""
src/supervisor/lease.py — Execution leases (HOD-707).

The gap this closes: Python cannot kill a thread. A worker that blows its
deadline is abandoned by the Supervisor and quarantined in the Registry —
but "quarantined" meant "no NEW work is routed to it". The abandoned thread
keeps executing, and if it wakes up later it could still commit writes the
fleet has already routed around. Detection without containment.

The lease turns that into a safety property without pretending threads are
killable:

    issue  → the Supervisor grants a lease before dispatching bounded work
    check  → every side-effecting write validates its lease IMMEDIATELY
             before committing (the gateway enforces this; the worker's
             cooperation is not part of the guarantee)
    revoke → the Supervisor revokes the lease the moment it abandons the
             task — BEFORE quarantine, before reroute
    deny   → a woken worker's late commit fails with a structured denial

The abandoned worker may compute forever. It can no longer commit.

Lease state is a FOLD over appended lease events — issued, revoked,
released — the same discipline as the grant log: nothing is mutated,
revocation is a new event, and "is this lease valid at t" is a fold with a
timestamp. The default ledger is process-local, which is a stated limit of
the fleet control plane (FINDINGS 2026-08-12, carried limit #3), not a
hidden one; the fold shape is what a Firestore-backed ledger shares.
"""

import uuid
import threading
from typing import Dict, List, Literal, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel


class LeaseEvent(BaseModel):
    event_id: str
    lease_id: str
    agent_id: str
    task_id: str
    kind: Literal["issued", "revoked", "released"]
    # Present on "issued": the instant after which the lease is invalid even
    # if nobody revokes it. A lease that outlives its task's deadline would
    # let a hung worker commit during the gap between deadline and detection.
    expires_at: Optional[datetime] = None
    # Present on "revoked": why the supervisor pulled it.
    reason: Optional[str] = None
    issued_at: datetime


class LeaseState(BaseModel):
    lease_id: str
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str = "nonexistent"  # "active" | "revoked" | "released" | "expired" | "nonexistent"
    expires_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


class LeaseLedger:
    """
    Append-only lease event log with a fold. Thread-safe: the Supervisor
    revokes from its own thread while the worker may be mid-check.
    """

    def __init__(self):
        self._events: List[LeaseEvent] = []
        self._lock = threading.Lock()

    def _append(self, event: LeaseEvent) -> None:
        with self._lock:
            if any(e.event_id == event.event_id for e in self._events):
                raise ValueError(f"Duplicate lease event id '{event.event_id}' — the ledger is append-only.")
            self._events.append(event)

    def issue(self, agent_id: str, task_id: str, ttl_seconds: float) -> str:
        lease_id = f"lease-{uuid.uuid4()}"
        now = datetime.now(timezone.utc)
        self._append(LeaseEvent(
            event_id=f"lev-{uuid.uuid4()}",
            lease_id=lease_id, agent_id=agent_id, task_id=task_id,
            kind="issued", expires_at=now + timedelta(seconds=ttl_seconds),
            issued_at=now,
        ))
        return lease_id

    def revoke(self, lease_id: str, reason: str) -> None:
        state = self.state(lease_id)
        self._append(LeaseEvent(
            event_id=f"lev-{uuid.uuid4()}",
            lease_id=lease_id,
            agent_id=state.agent_id or "unknown",
            task_id=state.task_id or "unknown",
            kind="revoked", reason=reason,
            issued_at=datetime.now(timezone.utc),
        ))

    def release(self, lease_id: str) -> None:
        state = self.state(lease_id)
        self._append(LeaseEvent(
            event_id=f"lev-{uuid.uuid4()}",
            lease_id=lease_id,
            agent_id=state.agent_id or "unknown",
            task_id=state.task_id or "unknown",
            kind="released",
            issued_at=datetime.now(timezone.utc),
        ))

    def state(self, lease_id: str, at: Optional[datetime] = None) -> LeaseState:
        """Pure fold. Terminal events win; expiry applies even unrevoked."""
        at = at or datetime.now(timezone.utc)
        with self._lock:
            events = sorted((e for e in self._events if e.lease_id == lease_id),
                            key=lambda e: (e.issued_at, e.event_id))
        state = LeaseState(lease_id=lease_id)
        for ev in events:
            state.agent_id = ev.agent_id
            state.task_id = ev.task_id
            if ev.kind == "issued":
                state.status = "active"
                state.expires_at = ev.expires_at
            elif ev.kind == "revoked":
                state.status = "revoked"
                state.revoked_reason = ev.reason
            elif ev.kind == "released":
                state.status = "released"
        if state.status == "active" and state.expires_at is not None and at > state.expires_at:
            state.status = "expired"
        return state

    def is_valid(self, lease_id: Optional[str], at: Optional[datetime] = None) -> bool:
        if not lease_id:
            return False
        return self.state(lease_id, at=at).status == "active"

    def events_for(self, lease_id: str) -> List[LeaseEvent]:
        with self._lock:
            return [e for e in self._events if e.lease_id == lease_id]
