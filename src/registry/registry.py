"""
src/registry/registry.py — Agent Registry (HOD-330, HOD-709).

Publications, heartbeats, and deregistrations are APPENDED EVENTS over a
pluggable store (Firestore live, in-memory offline); discovery is a fold.
Until 2026-08-14 the registry was a Python dict rebuilt per run — an
in-process catalog, not a durable enterprise registry — and quarantine
"deregistered" an agent by `del`eting the dict entry, destroying the very
record that would show WHEN and WHY the agent left the fleet. Now
deregistration is an event with a reason, the publication history
survives it, and a fresh process folds the same registry state a prior
process published.

Role-scoped NON-DISCLOSURE is unchanged and load-bearing: an unauthorized
discover() returns [] — the caller is not told the target exists.
"""

import uuid
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime, timezone
from pydantic import BaseModel

from src.schema.iam_policy import is_action_permitted, AGENT_SA_MAP
from src.memory.event_store import InMemoryEventStore


class AgentPublication(BaseModel):
    agent_id: str
    name: str
    version: str
    owning_function: str  # rights_custodian, licensing_negotiator, evidence_agent, revocation_propagator, consent_arbiter
    role: str
    scopes: List[str]
    # Durable-registry fields (HOD-709). `endpoint` is where the agent is
    # invoked — a URL for a deployed worker, None for an in-process agent
    # (stated, not faked). `service_account` is the workload identity the
    # publication claims; discovery hands it back so a caller can verify the
    # boundary it is about to cross.
    endpoint: Optional[str] = None
    service_account: Optional[str] = None
    capabilities: List[str] = []
    status: str = "active"  # folded: "active" | "deregistered"
    registered_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None


class RegistryEvent(BaseModel):
    event_id: str
    agent_id: str
    kind: Literal["registered", "heartbeat", "deregistered"]
    publication: Optional[AgentPublication] = None  # on "registered"
    reason: Optional[str] = None                    # on "deregistered"
    recorded_at: datetime


class AgentRegistry:
    """
    Correction 5(b): discover(role, requesting_sa) returns EMPTY RESULT ([]) if requesting_sa
    is unauthorized to invoke the target agent role. Does NOT throw error or leak existence.
    """

    COLLECTION = "agent_registry_events"

    def __init__(self, store=None):
        self._store = store if store is not None else InMemoryEventStore()
        # Matrix of authorized inter-agent invocations: {requesting_role: [roles it may invoke]}.
        #
        # rights_custodian -> revocation_propagator is the artist's revocation
        # path: the artist owns the work and initiates termination. Invoking is
        # not sharing — the custodian passes an opaque work_id and use_type, and
        # the propagator resolves affected grants itself, so no identity crosses
        # the boundary (Phase 2 correction 3).
        #
        # licensing_negotiator -> revocation_propagator is deliberately ABSENT:
        # a buyer's negotiator must not be able to trigger revocations, and the
        # registry answers such a query with [] rather than disclosing that the
        # propagator exists at all.
        #
        # consent_arbiter appears as a TARGET for the supervisor only: the
        # arbiter is fed typed assertions by the incident engine; no domain
        # agent may invoke it directly, and it invokes nobody.
        self._allowed_invocations: Dict[str, List[str]] = {
            "rights_custodian": ["rights_custodian", "revocation_propagator"],
            "licensing_negotiator": ["licensing_negotiator", "rights_custodian"],
            "evidence_agent": ["evidence_agent"],
            "revocation_propagator": ["revocation_propagator", "evidence_agent"],
            "supervisor": ["rights_custodian", "licensing_negotiator", "evidence_agent",
                           "revocation_propagator", "consent_arbiter"],
            "consent_arbiter": ["consent_arbiter"],
        }

    # --- event appends -----------------------------------------------------

    def _append(self, event: RegistryEvent) -> None:
        self._store.append(self.COLLECTION, event.event_id, event.model_dump(mode="json"))

    def register(self, publication: AgentPublication) -> None:
        now = datetime.now(timezone.utc)
        pub = publication.model_copy(update={
            "registered_at": publication.registered_at or now,
            "status": "active",
        })
        self._append(RegistryEvent(
            event_id=f"reg-{uuid.uuid4()}", agent_id=pub.agent_id,
            kind="registered", publication=pub, recorded_at=now))

    def heartbeat(self, agent_id: str) -> None:
        self._append(RegistryEvent(
            event_id=f"reg-{uuid.uuid4()}", agent_id=agent_id,
            kind="heartbeat", recorded_at=datetime.now(timezone.utc)))

    def deregister(self, agent_id: str, reason: str) -> None:
        """Deregistration is an EVENT with a reason, never a deletion — the
        publication history survives, which is the whole audit point."""
        self._append(RegistryEvent(
            event_id=f"reg-{uuid.uuid4()}", agent_id=agent_id,
            kind="deregistered", reason=reason, recorded_at=datetime.now(timezone.utc)))

    # --- the fold ----------------------------------------------------------

    def _fold(self) -> Dict[str, AgentPublication]:
        rows = self._store.read(self.COLLECTION)
        events = sorted((RegistryEvent(**r) for r in rows),
                        key=lambda e: (e.recorded_at, e.event_id))
        state: Dict[str, AgentPublication] = {}
        for ev in events:
            if ev.kind == "registered" and ev.publication is not None:
                state[ev.agent_id] = ev.publication
            elif ev.kind == "heartbeat" and ev.agent_id in state:
                state[ev.agent_id] = state[ev.agent_id].model_copy(
                    update={"last_heartbeat": ev.recorded_at})
            elif ev.kind == "deregistered" and ev.agent_id in state:
                state[ev.agent_id] = state[ev.agent_id].model_copy(
                    update={"status": "deregistered"})
        return state

    def publications(self, include_deregistered: bool = False) -> Dict[str, AgentPublication]:
        state = self._fold()
        if include_deregistered:
            return state
        return {aid: pub for aid, pub in state.items() if pub.status == "active"}

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self.publications()

    def discover(self, target_role: str, requesting_role_key: str) -> List[AgentPublication]:
        """
        Returns ACTIVE agents matching target_role IF requesting_role_key is authorized.
        Correction 5(b): If unauthorized, returns [] (EMPTY RESULT) to avoid disclosing agent existence.
        A quarantined (deregistered) agent is equally undisclosed: it does not
        exist to discovery for the remainder of the run.
        """
        allowed_targets = self._allowed_invocations.get(requesting_role_key, [])
        if target_role not in allowed_targets:
            # Silent non-disclosure: return empty list
            return []

        return [pub for pub in self.publications().values()
                if pub.owning_function == target_role or pub.role == target_role]
