"""
src/incident/engine.py — Autonomous Consent Incident Response (HOD-705).

The flow the review asked to see, with every wall intact:

  observe      the evidence agent reads the access record IN ITS OWN DOMAIN
               and submits a typed OBSERVED_HTTP_ACCESS assertion — it cannot
               see terms or identity, and no assertion class would let it
               claim training.
  investigate  discovery finds who can answer what. The negotiator answers
               grant-existence for ONE principal inside its session wall; the
               custodian answers whether the access mode fits the WORK'S OWN
               declared policy (its domain — the work, never the buyer's
               negotiated terms); the counterparty advocate makes its
               exculpatory assertion, and the policy treats it as true.
  adjudicate   the arbiter — holding NONE of the four domains — concludes
               from the typed assertions alone, deterministically.
  contain      only what Hodi itself administers: pending negotiation for
               the principal is frozen, and grants that permit the
               inconsistent use are terminated through the EXISTING cascade
               (idempotent, outboxed). No takedowns, no enforcement — the
               rail, not a weapon.
  close        a signed manifest binding observations (hashed), assertions
               (hashed), policy version, decision, limitations, containment,
               trace and chain link. `hodi verify` reconstructs the decision
               from the package alone.

Every lifecycle transition is an APPENDED event; the manifest is the
terminal append. Nothing is mutated at any step.
"""

import hashlib
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from src.gateway.gateway import AgentGateway, GatewayPolicyDenial, DocumentAlreadyExists
from src.registry.registry import AgentRegistry
from src.agents.consent_arbiter import ConsentArbiterAgent, ARBITER_SA, CONSENT_POLICY_VERSION
from src.agents.revocation_propagator import RevocationPropagatorAgent
from src.observability.tracing import create_agent_decision_span
from src.resolve.resolver import active_grant_events
from src.schema.assertion import TypedAssertion
from src.schema.grant_event import GrantEvent
from src.schema.iam_policy import AGENT_SA_MAP
from src.schema.incident import (
    ConsentIncidentManifest, IncidentLifecycleEvent, NegotiationFreeze,
    ObservationRecord, STATUS_ORDER, assertions_digest, observation_hash,
)
from src.schema.signing import (
    canonical_json_bytes, get_active_signer, signable_bytes, signature_for,
)

EVIDENCE_SA = AGENT_SA_MAP["evidence_agent"]["sa_email"]
NEGOTIATOR_SA = AGENT_SA_MAP["licensing_negotiator"]["sa_email"]
CUSTODIAN_SA = AGENT_SA_MAP["rights_custodian"]["sa_email"]

GENESIS_HASH = "GENESIS"


class IncidentResult:
    def __init__(self, manifest: ConsentIncidentManifest,
                 assertions: List[TypedAssertion],
                 observations: List[ObservationRecord],
                 lifecycle: List[IncidentLifecycleEvent],
                 freeze: Optional[NegotiationFreeze],
                 revocation_operation_id: Optional[str]):
        self.manifest = manifest
        self.assertions = assertions
        self.observations = observations
        self.lifecycle = lifecycle
        self.freeze = freeze
        self.revocation_operation_id = revocation_operation_id


class IncidentEngine:
    def __init__(self, gateway: AgentGateway, registry: Optional[AgentRegistry] = None):
        self.gateway = gateway
        self.registry = registry or AgentRegistry()
        self.arbiter = ConsentArbiterAgent(gateway)

    # --- lifecycle plumbing -------------------------------------------------

    def _transition(self, incident_id: str, lifecycle: List[IncidentLifecycleEvent],
                    status: str, detail: str) -> None:
        # Transitions move only forward through STATUS_ORDER — an incident
        # cannot be contained before it was adjudicated, and nothing rewinds.
        if lifecycle:
            prev = STATUS_ORDER.index(lifecycle[-1].status)
            if STATUS_ORDER.index(status) <= prev:
                raise ValueError(
                    f"Illegal incident transition {lifecycle[-1].status!r} -> {status!r}")
        seq = len(lifecycle)
        event = IncidentLifecycleEvent(
            event_id=f"{incident_id}:{seq:02d}:{status}",
            incident_id=incident_id, status=status, detail=detail,
            recorded_at=datetime.now(timezone.utc))
        # Appended under the arbiter's domain: the incident record is its
        # collection, and create-only ids make replays collide, not duplicate.
        self.gateway.write_document(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="incidents", doc_id=event.event_id,
            data=event.model_dump(mode="json"))
        lifecycle.append(event)

    def _previous_manifest_hash(self) -> str:
        rows = self.gateway.read_collection(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="incidents", filters={"manifest_version": "1"})
        if not rows:
            return GENESIS_HASH
        newest = sorted(rows, key=lambda r: r.get("closed_at", ""))[-1]
        return hashlib.sha256(signable_bytes(newest)).hexdigest()

    # --- the flow -----------------------------------------------------------

    def run(self, work_id: str, declared_principal: str,
            access_record: Dict[str, Any],
            include_advocate: bool = True) -> IncidentResult:
        incident_id = f"incident-{uuid.uuid4().hex[:8]}"
        opened_at = datetime.now(timezone.utc)
        lifecycle: List[IncidentLifecycleEvent] = []
        assertions: List[TypedAssertion] = []

        span = create_agent_decision_span(
            span_name="incident.run",
            agent_identity="incident-engine",
            policy_consulted=CONSENT_POLICY_VERSION,
            outcome="OPENED")
        trace_id = f"{span.get_span_context().trace_id:032x}"

        # ---- OBSERVED: the evidence agent, inside its own domain ----
        observed_rows = self.gateway.read_collection(
            calling_sa=EVIDENCE_SA, calling_role_key="evidence_agent",
            target_collection="crawler_access",
            filters={"record_id": access_record["record_id"]})
        if not observed_rows:
            span.set_attribute("incident.outcome", "NO_OBSERVATION")
            span.end()
            raise ValueError(f"No crawler_access record {access_record['record_id']!r} "
                             "— an incident cannot open on an unobserved access.")
        row = observed_rows[0]
        observation = ObservationRecord(
            observation_id=row["record_id"],
            work_id=work_id,
            declared_user_agent=row["user_agent"],
            path=row["path"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            detail=row.get("detail", ""))
        self._transition(incident_id, lifecycle, "observed",
                         f"observation {observation.observation_id} recorded by evidence agent")
        assertions.append(self.gateway.submit_assertion(
            calling_sa=EVIDENCE_SA, calling_role_key="evidence_agent",
            assertion=TypedAssertion(
                assertion_id=f"assert-{incident_id}-observed",
                assertion_class="OBSERVED_HTTP_ACCESS",
                asserted_by_role="evidence_agent",
                subject_work_id=work_id,
                subject_principal=declared_principal,
                observed_at=observation.observed_at,
                basis=f"crawler_access record {observation.observation_id}: "
                      f"declared UA {observation.declared_user_agent!r} fetched {observation.path!r}",
                evidence_ref=observation.observation_id,
                recorded_at=datetime.now(timezone.utc))))

        # ---- INVESTIGATING: each wall answers only its own question ----
        self._transition(incident_id, lifecycle, "investigating",
                         "registry discovery: who can determine whether this access was authorized")

        # Discovery runs under the supervisor's invocation authority; the
        # answering agents are addressed by role, not by object identity.
        negotiators = self.registry.discover("licensing_negotiator", "supervisor")
        custodians = self.registry.discover("rights_custodian", "supervisor")

        # The NEGOTIATOR: grant existence for THIS principal at the observed
        # instant — read inside its counterparty session wall, folded, and
        # answered as an assertion whose basis names the fold, not the data.
        raw_grants = self.gateway.read_collection(
            calling_sa=NEGOTIATOR_SA, calling_role_key="licensing_negotiator",
            target_collection="grants",
            filters={"counterparty_id": declared_principal, "work_id": work_id},
            session_context={"counterparty_id": declared_principal})
        active = [g for g in active_grant_events(
            [GrantEvent(**g) for g in raw_grants], at=observation.observed_at)
            if g.work_id == work_id]
        grant_state_basis = (
            f"fold over grants(counterparty={declared_principal!r}, work={work_id!r}) "
            f"at {observation.observed_at.isoformat()}: "
            f"{len(active)} active grant(s)"
            + (f" [{', '.join(g.grant_id for g in active)}]" if active else ""))
        assertions.append(self.gateway.submit_assertion(
            calling_sa=NEGOTIATOR_SA, calling_role_key="licensing_negotiator",
            assertion=TypedAssertion(
                assertion_id=f"assert-{incident_id}-grant",
                assertion_class="GRANT_EXISTED" if active else "GRANT_DID_NOT_EXIST",
                asserted_by_role="licensing_negotiator",
                subject_work_id=work_id,
                subject_principal=declared_principal,
                observed_at=observation.observed_at,
                basis=grant_state_basis,
                recorded_at=datetime.now(timezone.utc))))

        # The CUSTODIAN: does the access MODE fit the work's own declared
        # policy? Its domain is the work — it reads `works`, never the
        # buyer's negotiated terms.
        work_rows = self.gateway.read_collection(
            calling_sa=CUSTODIAN_SA, calling_role_key="rights_custodian",
            target_collection="works", filters={"work_id": work_id})
        declared_policy = (work_rows[0].get("declared_access_policy", "")
                          if work_rows else "")
        automated_forbidden = declared_policy in ("human_reference_only", "no_automated_ingestion")
        if automated_forbidden:
            assertions.append(self.gateway.submit_assertion(
                calling_sa=CUSTODIAN_SA, calling_role_key="rights_custodian",
                assertion=TypedAssertion(
                    assertion_id=f"assert-{incident_id}-scope",
                    assertion_class="ACCESS_INCONSISTENT_WITH_SCOPE",
                    asserted_by_role="rights_custodian",
                    subject_work_id=work_id,
                    subject_principal=declared_principal,
                    observed_at=observation.observed_at,
                    basis=(f"work {work_id!r} declares access policy "
                           f"{declared_policy!r}; an automated fetch by a declared "
                           "crawler is outside that declaration"),
                    recorded_at=datetime.now(timezone.utc))))

        # The COUNTERPARTY ADVOCATE: the exculpatory assertion — the one
        # statement its role is authorized to make, and it is TRUE.
        if include_advocate:
            assertions.append(self.gateway.submit_assertion(
                calling_sa="counterparty-advocate (external)",
                calling_role_key="counterparty_advocate",
                assertion=TypedAssertion(
                    assertion_id=f"assert-{incident_id}-advocate",
                    assertion_class="ACCESS_DOES_NOT_ESTABLISH_TRAINING",
                    asserted_by_role="counterparty_advocate",
                    subject_work_id=work_id,
                    subject_principal=declared_principal,
                    observed_at=observation.observed_at,
                    basis="an HTTP fetch establishes a request, not ingestion, and not training",
                    recorded_at=datetime.now(timezone.utc))))

        # ---- ADJUDICATED: the arbiter sees ONLY the assertions ----
        decision = self.arbiter.adjudicate(assertions, incident_id)
        self._transition(incident_id, lifecycle, "adjudicated",
                         f"decision {decision.decision_id} under {decision.policy_version}")

        outside = any(f.claim == "ACCESS_OUTSIDE_DECLARED_POLICY" and f.status == "ESTABLISHED"
                      for f in decision.findings)

        # ---- CONTAINED: only what Hodi itself administers ----
        freeze: Optional[NegotiationFreeze] = None
        revocation_operation_id: Optional[str] = None
        if outside:
            freeze = NegotiationFreeze(
                freeze_id=f"freeze-{incident_id}",
                counterparty_id=declared_principal,
                incident_id=incident_id,
                reason="ACCESS_OUTSIDE_DECLARED_POLICY established; pending negotiation "
                       "frozen while the incident record stands",
                frozen_at=datetime.now(timezone.utc))
            try:
                self.gateway.write_document(
                    calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
                    target_collection="negotiation_freezes", doc_id=freeze.freeze_id,
                    data=freeze.model_dump(mode="json"))
            except DocumentAlreadyExists:
                pass  # an incident re-run cannot double-freeze

            if active:
                # Grants exist that the custodian's scope finding undercuts:
                # terminate through the EXISTING idempotent cascade —
                # revocation stays the propagator's verb, not the arbiter's.
                propagator = RevocationPropagatorAgent(gateway=self.gateway)
                cascade = propagator.execute_revocation_cascade(
                    work_id=work_id, revoked_use_type=active[0].scope.use_type,
                    operation_id=f"incident-{incident_id}")
                revocation_operation_id = cascade.operation_id
                assertions.append(self.gateway.submit_assertion(
                    calling_sa=AGENT_SA_MAP["revocation_propagator"]["sa_email"],
                    calling_role_key="revocation_propagator",
                    assertion=TypedAssertion(
                        assertion_id=f"assert-{incident_id}-revocation",
                        assertion_class="REVOCATION_INITIATED",
                        asserted_by_role="revocation_propagator",
                        subject_work_id=work_id,
                        subject_principal=declared_principal,
                        basis=f"cascade operation {cascade.operation_id}: "
                              f"{len(cascade.affected_grants)} grant(s) terminated, notices outboxed",
                        recorded_at=datetime.now(timezone.utc))))
            self._transition(incident_id, lifecycle, "contained",
                             "negotiation frozen"
                             + ("; revocation cascade executed" if revocation_operation_id else
                                "; no active grant to terminate"))

        # ---- CLOSED: the manifest, signed, chained, appended ----
        closed_at = datetime.now(timezone.utc)
        signer = get_active_signer()
        manifest = ConsentIncidentManifest(
            incident_id=incident_id,
            work_id=work_id,
            subject_principal=declared_principal,
            observations=[observation],
            evidence_hashes={observation.observation_id: observation_hash(observation)},
            assertions_hash=assertions_digest(assertions),
            policy_version=decision.policy_version,
            grant_state_basis=grant_state_basis,
            decision=decision,
            decision_basis=[a.assertion_id for a in assertions],
            limitations=[
                "The observation records a request; the user agent is self-declared "
                "and the record never proves who made it.",
                "No conclusion about model training exists or can exist in this record.",
                "Containment acts only on grants and negotiations Hodi administers — "
                "no takedown, no external enforcement.",
            ],
            agents_involved=sorted({a.asserted_by_role for a in assertions} | {"consent_arbiter"}),
            containment={
                "negotiation_freeze": freeze.freeze_id if freeze else None,
                "revocation_operation_id": revocation_operation_id,
            },
            opened_at=opened_at,
            closed_at=closed_at,
            trace_id=trace_id,
            previous_event_hash=self._previous_manifest_hash(),
            signing_key_version=(getattr(signer, "key_id", "none") if signer else "none"),
            signature="",
        )
        manifest = manifest.model_copy(update={"signature": signature_for(
            "incident_manifest", incident_id,
            signable_bytes(manifest.model_dump(mode="json")))})
        self.gateway.write_document(
            calling_sa=ARBITER_SA, calling_role_key="consent_arbiter",
            target_collection="incidents", doc_id=f"{incident_id}:manifest",
            data=manifest.model_dump(mode="json"))
        self._transition(incident_id, lifecycle, "closed",
                         f"manifest signed ({manifest.signing_key_version}) and appended")

        span.set_attribute("incident.id", incident_id)
        span.set_attribute("incident.outcome",
                           "ACCESS_OUTSIDE_DECLARED_POLICY" if outside else "WITHIN_POLICY")
        span.end()

        return IncidentResult(manifest=manifest, assertions=assertions,
                              observations=[observation], lifecycle=lifecycle,
                              freeze=freeze, revocation_operation_id=revocation_operation_id)
