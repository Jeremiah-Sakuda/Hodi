"""
src/agents/consent_arbiter.py — the fifth agent (HOD-704).

The arbiter holds NONE of the four conflict domains. It receives typed
assertions plus a policy version — never raw evidence, never identity,
never commercial terms — and evaluates DETERMINISTICALLY. Its entire
input is what constrained agents were each willing to sign their name to
inside their own walls; its entire output is what those assertions
support and not one claim more.

Determinism is load-bearing twice over: it keeps a model out of the
adjudication path (the same thesis as "the model interprets intent, the
lattice decides permission"), and it makes every decision REPRODUCIBLE —
`hodi verify` re-runs this exact function over the packaged assertions
and requires the same conclusions, so an incident record proves itself
instead of asking to be trusted.
"""

import uuid
from typing import Dict, Any, List
from datetime import datetime, timezone

from src.gateway.gateway import AgentGateway
from src.schema.assertion import (
    TypedAssertion, IncidentDecision, ClaimFinding, NOT_DETERMINABLE_TRAINING,
)

ARBITER_SA = "consent-arbiter-sa@hodi-2026.iam.gserviceaccount.com"

CONSENT_POLICY_VERSION = "consent_policy_v1"


def adjudicate_assertions(assertions: List[TypedAssertion], incident_id: str,
                          decision_id: str = None,
                          decided_at: datetime = None) -> IncidentDecision:
    """
    The deterministic adjudication rule, as a MODULE-LEVEL function on
    purpose: the verifier re-runs precisely this over a package's assertions
    and must reproduce the recorded decision. Policy, in words:

      ACCESS_OUTSIDE_DECLARED_POLICY is ESTABLISHED iff an access was
      observed (OBSERVED_HTTP_ACCESS) and, for that subject, either the
      negotiator asserts no applicable grant existed at the instant
      (GRANT_DID_NOT_EXIST) or the custodian asserts the access mode falls
      outside the declared scope (ACCESS_INCONSISTENT_WITH_SCOPE) — and no
      GRANT_EXISTED assertion covers it.

      ACCESS_WITHIN_DECLARED_POLICY is ESTABLISHED iff an access was
      observed and a GRANT_EXISTED assertion covers it, uncontradicted.

      MODEL_TRAINING_OCCURRED is not adjudicated. It is carried on every
      decision as NOT_ESTABLISHED with the reason, whatever else is found —
      including when the counterparty advocate's exculpatory assertion is
      present, which this policy treats as TRUE BY CONSTRUCTION.
    """
    classes = {a.assertion_class for a in assertions}
    basis_of = lambda cls: [a.assertion_id for a in assertions if a.assertion_class == cls]  # noqa: E731

    observed = "OBSERVED_HTTP_ACCESS" in classes
    no_grant = "GRANT_DID_NOT_EXIST" in classes
    grant_existed = "GRANT_EXISTED" in classes
    scope_inconsistent = "ACCESS_INCONSISTENT_WITH_SCOPE" in classes

    findings: List[ClaimFinding] = []

    outside = observed and (no_grant or scope_inconsistent) and not (grant_existed and not scope_inconsistent)
    findings.append(ClaimFinding(
        claim="ACCESS_OUTSIDE_DECLARED_POLICY",
        status="ESTABLISHED" if outside else "NOT_ESTABLISHED",
        basis=(basis_of("OBSERVED_HTTP_ACCESS")
               + basis_of("GRANT_DID_NOT_EXIST")
               + basis_of("ACCESS_INCONSISTENT_WITH_SCOPE")) if outside else [],
    ))

    within = observed and grant_existed and not scope_inconsistent and not no_grant
    findings.append(ClaimFinding(
        claim="ACCESS_WITHIN_DECLARED_POLICY",
        status="ESTABLISHED" if within else "NOT_ESTABLISHED",
        basis=(basis_of("OBSERVED_HTTP_ACCESS") + basis_of("GRANT_EXISTED")) if within else [],
    ))

    not_determinable = {"MODEL_TRAINING_OCCURRED": NOT_DETERMINABLE_TRAINING}
    if "ACCESS_DOES_NOT_ESTABLISH_TRAINING" in classes:
        not_determinable["MODEL_TRAINING_OCCURRED"] = (
            NOT_DETERMINABLE_TRAINING
            + " The counterparty advocate asserted this limit explicitly "
            f"({', '.join(basis_of('ACCESS_DOES_NOT_ESTABLISH_TRAINING'))}); the policy "
            "treats it as true by construction — it did not need to be argued.")

    return IncidentDecision(
        decision_id=decision_id or f"dec-{uuid.uuid4()}",
        incident_id=incident_id,
        policy_version=CONSENT_POLICY_VERSION,
        findings=findings,
        not_determinable=not_determinable,
        decided_at=decided_at or datetime.now(timezone.utc),
    )


class ConsentArbiterAgent:
    """The agent wrapper: the deterministic rule above, plus the paired
    negative reads that PROVE the arbiter's walls at the gateway."""

    def __init__(self, gateway: AgentGateway):
        self.gateway = gateway

    def adjudicate(self, assertions: List[TypedAssertion], incident_id: str) -> IncidentDecision:
        return adjudicate_assertions(assertions, incident_id)

    # --- paired positives and negatives, same pattern as every other agent ---

    def record_incident(self, doc_id: str, data: Dict[str, Any], lease_id: str = None) -> None:
        """Paired positive: the incident record is the arbiter's own domain."""
        self.gateway.write_document(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="incidents", doc_id=doc_id, data=data, lease_id=lease_id)

    def read_raw_evidence(self) -> Any:
        """Paired negative: the arbiter CANNOT read raw evidence — assertions only."""
        return self.gateway.read_collection(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="crawler_access")

    def read_buyer_terms(self, counterparty_id: str) -> Any:
        """Paired negative: the arbiter CANNOT read commercial terms."""
        return self.gateway.read_collection(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="buyer_terms", filters={"counterparty_id": counterparty_id},
            session_context={"counterparty_id": counterparty_id})

    def read_artist_identity(self) -> Any:
        """Paired negative: the arbiter CANNOT hold identity."""
        return self.gateway.read_collection(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="artists")

    def rewrite_grant_history(self, doc_id: str, data: Dict[str, Any]) -> None:
        """Paired negative (HOD-704 AC): the arbiter has NO write path to the
        history it rules on."""
        self.gateway.write_document(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="grants", doc_id=doc_id, data=data)
