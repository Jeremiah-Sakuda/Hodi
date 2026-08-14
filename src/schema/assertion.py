"""
src/schema/assertion.py — typed assertions and the closed conclusion
vocabulary (HOD-703, HOD-704).

Zero trust applied to EPISTEMIC authority: alongside "who may read which
collection" (iam_policy.py), the fleet now declares who may CLAIM what.
An assertion is a typed, attributed, bounded statement — never free text —
and its class comes from a closed vocabulary.

THE STRUCTURAL POINT, same shape as EvidenceRecord.class: there is NO
assertion class for training-set membership. `MODEL_TRAINED_ON_WORK` is
not a value of AssertionClass, so no agent — whatever its authority —
can submit the claim as data; the schema refuses it before the authority
matrix is even consulted. The arbiter's conclusion vocabulary repeats the
same construction: EstablishableClaim has no training value, and the
training question appears ONLY in `not_determinable`, whose entries are
validated to state NOT_ESTABLISHED. "Established: model training" is not
a forbidden output — it is an inexpressible one.
"""

from typing import Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

# What an agent may SUBMIT. Each class belongs to exactly the role whose
# epistemic position supports it — the authority matrix is
# src/schema/assertion_authority.py, enforced at the gateway.
AssertionClass = Literal[
    "OBSERVED_HTTP_ACCESS",                # evidence agent: a request happened, with these attributes
    "GRANT_EXISTED",                       # negotiator: an applicable grant existed at the instant
    "GRANT_DID_NOT_EXIST",                 # negotiator: no applicable grant existed at the instant
    "ACCESS_INCONSISTENT_WITH_SCOPE",      # rights custodian: the access mode falls outside the declared scope
    "REVOCATION_INITIATED",                # propagator: termination has been initiated for the affected grants
    "ACCESS_DOES_NOT_ESTABLISH_TRAINING",  # counterparty advocate: the exculpatory statement — and it is TRUE
]

# What the arbiter may ESTABLISH. No training value exists here either.
EstablishableClaim = Literal[
    "ACCESS_OUTSIDE_DECLARED_POLICY",
    "ACCESS_WITHIN_DECLARED_POLICY",
]

CLAIM_LIMIT_ASSERTION = (
    "A typed assertion states what its class can carry and nothing more. No "
    "assertion class exists for training-set membership; this system cannot "
    "receive that claim as data."
)


class TypedAssertion(BaseModel):
    assertion_id: str
    assertion_class: AssertionClass
    asserted_by_role: str
    # Opaque identifiers only. An assertion crosses conflict walls, so it may
    # carry the work's id and the principal's id — never artist identity,
    # never commercial terms, never a raw evidence record.
    subject_work_id: str
    subject_principal: Optional[str] = None
    observed_at: Optional[datetime] = None
    # What the assertion rests on, as a REFERENCE (an evidence id, a fold
    # description), never the underlying data itself.
    basis: str
    evidence_ref: Optional[str] = None
    limits: str = CLAIM_LIMIT_ASSERTION
    recorded_at: datetime


class ClaimFinding(BaseModel):
    claim: EstablishableClaim
    status: Literal["ESTABLISHED", "NOT_ESTABLISHED"]
    basis: List[str] = Field(default_factory=list)


NOT_DETERMINABLE_TRAINING = (
    "NOT_ESTABLISHED — outside this system's epistemic authority. Crawler "
    "access does not establish ingestion; ingestion does not establish "
    "training; no assertion class can carry the claim and no conclusion "
    "class can establish it."
)


class IncidentDecision(BaseModel):
    decision_id: str
    incident_id: str
    policy_version: str
    findings: List[ClaimFinding]
    # The permanent epistemic boundary, restated ON EVERY DECISION. Keys are
    # questions this system refuses to answer; values must say so. A decision
    # that tried to smuggle "ESTABLISHED" into this map fails validation.
    not_determinable: Dict[str, str] = Field(default_factory=lambda: {
        "MODEL_TRAINING_OCCURRED": NOT_DETERMINABLE_TRAINING,
    })
    decided_at: datetime

    @model_validator(mode="after")
    def _not_determinable_stays_not_established(self) -> "IncidentDecision":
        for question, answer in self.not_determinable.items():
            if not answer.startswith("NOT_ESTABLISHED"):
                raise ValueError(
                    f"not_determinable[{question!r}] must state NOT_ESTABLISHED; "
                    f"got {answer[:40]!r}. This map exists to hold the questions "
                    "the system refuses to answer — it cannot be repurposed to "
                    "answer them.")
        if "MODEL_TRAINING_OCCURRED" not in self.not_determinable:
            raise ValueError(
                "Every IncidentDecision must carry the MODEL_TRAINING_OCCURRED "
                "boundary in not_determinable — removing it does not make the "
                "question answerable, it hides that it was asked.")
        return self
