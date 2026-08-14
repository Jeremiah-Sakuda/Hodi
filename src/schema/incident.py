"""
src/schema/incident.py — the consent incident record (HOD-705).

An incident is a lifecycle (observed → investigating → adjudicated →
contained → closed) recorded as APPENDED EVENTS, and its terminal artifact
is a ConsentIncidentManifest: everything needed to independently
reconstruct the decision — observations with their hashes, the typed
assertions each walled agent signed its name to, the policy version, the
deterministic decision, the stated limitations, the containment actually
executed, the trace, the chain link, and a signature.

The manifest asks to be CHECKED, not believed: `hodi verify` recomputes
the hashes, re-runs the arbiter's deterministic policy over the packaged
assertions, and requires the same conclusions.
"""

import hashlib
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from src.schema.assertion import TypedAssertion, IncidentDecision
from src.schema.signing import canonical_json_bytes

IncidentStatus = Literal["observed", "investigating", "adjudicated", "contained", "closed"]

# The only order a lifecycle may move in. The engine validates every
# transition against this — an incident cannot be "contained" before it was
# adjudicated, and nothing moves backwards.
STATUS_ORDER: List[str] = ["observed", "investigating", "adjudicated", "contained", "closed"]

OBSERVATION_CLAIM_LIMIT = (
    "Records that an HTTP request with these attributes was received. The user "
    "agent is self-declared; the record is evidence of a request having been "
    "made, never of who made it, and never of training."
)


class ObservationRecord(BaseModel):
    """What the evidence agent observed — attributable, not authenticated,
    and carrying its claim limit on its face."""
    observation_id: str
    work_id: str
    declared_user_agent: str
    path: str
    observed_at: datetime
    source: str = "crawler_access"
    detail: str = ""
    claim_limit: str = OBSERVATION_CLAIM_LIMIT


class IncidentLifecycleEvent(BaseModel):
    event_id: str
    incident_id: str
    status: IncidentStatus
    detail: str
    recorded_at: datetime


class ConsentIncidentManifest(BaseModel):
    manifest_version: str = "1"
    incident_id: str
    work_id: str
    subject_principal: str
    observations: List[ObservationRecord]
    # observation_id -> sha256 of the observation's canonical bytes. The
    # verifier recomputes every one; a single altered byte in any observation
    # breaks its hash, and the manifest signature covers the hashes.
    evidence_hashes: Dict[str, str]
    # sha256 over the canonical bytes of the assertion list, in order — the
    # assertions travel beside the manifest in the exported package and are
    # bound to it by this hash.
    assertions_hash: str
    policy_version: str
    # The negotiator's own statement of what its grant answer rests on. The
    # arbiter never saw the grants; the manifest says so instead of implying
    # otherwise.
    grant_state_basis: str
    decision: IncidentDecision
    decision_basis: List[str]
    limitations: List[str]
    agents_involved: List[str]
    containment: Dict[str, Any]
    opened_at: datetime
    closed_at: datetime
    trace_id: str
    previous_event_hash: str
    signing_key_version: str
    signature: str


def observation_hash(observation: ObservationRecord) -> str:
    return hashlib.sha256(canonical_json_bytes(observation.model_dump(mode="json"))).hexdigest()


def assertions_digest(assertions: List[TypedAssertion]) -> str:
    payload = canonical_json_bytes([a.model_dump(mode="json") for a in assertions])
    return hashlib.sha256(payload).hexdigest()


class NegotiationFreeze(BaseModel):
    """A containment directive: pending negotiation for this principal is
    frozen. Enforced at the API layer BEFORE the negotiator engages — the
    same cross-domain-gate pattern as the revocation ownership check."""
    freeze_id: str
    counterparty_id: str
    incident_id: str
    reason: str
    frozen_at: datetime
