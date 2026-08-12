import uuid
import base64
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from src.schema.scope import Scope, ScopeEvaluationResult, UseType
from src.schema.grant_event import GrantEvent, Receipt
from src.resolve.evaluator import permits
from src.resolve.resolver import active_grant_events
from src.gateway.prompt_inspector import PromptInspector
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.agents.revocation_propagator import RevocationPropagatorAgent, CascadeResult
from src.api.auth import (
    AuthenticatedCounterparty, CredentialStore, RequestAuthenticationError, authenticate,
    HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE
)

router = APIRouter()
armor = PromptInspector()

# The licensing negotiator agent acts under its own service account
NEGOTIATOR_SA = "licensing-negotiator@hodi-2026.iam.gserviceaccount.com"
PROPAGATOR_SA = "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com"
# Ownership is a RIGHTS-CUSTODIAN concern: it holds works and artist identity.
# The propagator must not — it cannot read `works` at all — so the "does this
# artist own this work" gate lives here, at the API layer, before delegation.
RIGHTS_CUSTODIAN_SA = "rights-custodian-sa@hodi-2026.iam.gserviceaccount.com"

# Injectable so tests never touch the production credential collection.
_credential_store = CredentialStore()

def set_credential_store(store) -> None:
    """Replaces the credential store (tests, offline runs)."""
    global _credential_store
    _credential_store = store


# Injectable gateway, so a test can supply offline documents (e.g. a `works`
# row) for the ownership check without a live Firestore. Defaults to a fresh
# AgentGateway per request in production.
_gateway_override = None

def set_gateway(gateway) -> None:
    """Replaces the gateway used by handlers (tests, offline runs). Pass None to reset."""
    global _gateway_override
    _gateway_override = gateway

def _get_gateway() -> "AgentGateway":
    return _gateway_override if _gateway_override is not None else AgentGateway()


async def _authenticate_or_403(request: Request,
                               claimed_counterparty_id: Optional[str],
                               required_principal_type: Optional[str] = None) -> AuthenticatedCounterparty:
    """
    Authenticates the caller from the signed-request headers and the RAW body
    bytes, and returns the VERIFIED counterparty.

    A body that claims a different counterparty than the credential is bound to
    is the cross-buyer attack; it is refused and logged as a structured denial
    event rather than silently downgraded to the caller's own identity.
    """
    try:
        auth = authenticate(
            key_id=request.headers.get(HEADER_KEY_ID, ""),
            issued_at=request.headers.get(HEADER_TIMESTAMP, ""),
            signature=request.headers.get(HEADER_SIGNATURE, ""),
            body=await request.body(),
            store=_credential_store,
        )
    except RequestAuthenticationError as e:
        raise HTTPException(status_code=403, detail=f"Request authentication failed: {e}")

    if claimed_counterparty_id is not None and claimed_counterparty_id != auth.counterparty_id:
        AgentGateway().log_identity_claim_denial(
            calling_sa=NEGOTIATOR_SA,
            authenticated_counterparty_id=auth.counterparty_id,
            claimed_counterparty_id=claimed_counterparty_id,
            key_id=auth.key_id,
        )
        raise HTTPException(
            status_code=403,
            detail=("Request authentication failed: the credential is not bound to the "
                    "claimed counterparty_id."),
        )

    if required_principal_type and auth.principal_type != required_principal_type:
        AgentGateway().log_principal_type_denial(
            calling_sa=NEGOTIATOR_SA, key_id=auth.key_id,
            principal_type=auth.principal_type,
            required_principal_type=required_principal_type,
            operation=request.url.path,
        )
        raise HTTPException(
            status_code=403,
            detail=(f"Request authentication failed: this operation requires a "
                    f"'{required_principal_type}' credential."),
        )
    return auth


def _verify_work_ownership_or_403(gateway: "AgentGateway", work_id: str,
                                  authenticated_artist_id: str) -> None:
    """
    Refuse the operation unless the authenticated artist owns `work_id`.

    Reads `works` as the RIGHTS CUSTODIAN — the only role permitted that
    collection; the revocation propagator is denied it, which is why the check
    cannot live inside the cascade. A missing work, or one owned by a different
    artist, is a uniform 403: an artist must not learn which work_ids exist or
    who owns them by probing this endpoint.
    """
    try:
        rows = gateway.read_collection(
            calling_sa=RIGHTS_CUSTODIAN_SA,
            calling_role_key="rights_custodian",
            target_collection="works",
            filters={"work_id": work_id},
        )
    except Exception:
        # A read failure must fail closed, never fall through to the cascade.
        raise HTTPException(status_code=403,
                            detail="Revocation denied: work ownership could not be verified.")

    owner = rows[0].get("artist_id") if rows else None
    if owner is None or owner != authenticated_artist_id:
        raise HTTPException(
            status_code=403,
            detail="Revocation denied: this credential does not own the specified work.")


class ScopeRequest(BaseModel):
    # Optional and NEVER trusted: if present it must match the authenticated
    # identity, which is derived from the verified credential (see the
    # X-Hodi-* signed-request headers on src/api/auth.py).
    counterparty_id: Optional[str] = None
    requested_scope: Scope
    raw_document_b64: str = Field(..., description="Base64 encoded raw buyer document bytes")

class LicenseResponse(BaseModel):
    permitted: bool
    licensable_set: List[str]
    explicit_exclusions: List[str]
    receipt: Optional[Receipt] = None
    anomaly_detected: bool = False
    inspector_engine: str = "unknown"

@router.post("/api/v1/license", response_model=LicenseResponse)
async def request_license(req: ScopeRequest, request: Request):
    # 1. Authenticate. The counterparty identity used everywhere below comes
    #    from the VERIFIED CREDENTIAL — never from the request body.
    auth = await _authenticate_or_403(request, claimed_counterparty_id=req.counterparty_id,
                                      required_principal_type="counterparty")

    # 2. Route raw post-extraction bytes through the Prompt Inspector
    try:
        raw_bytes = base64.b64decode(req.raw_document_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 document.")

    armor_result = armor.inspect(raw_bytes)
    anomaly_detected = armor_result.injection_detected

    # 3. Read active grants from real Firestore via AgentGateway
    gateway = AgentGateway()
    raw_grants = gateway.read_collection(
        calling_sa=NEGOTIATOR_SA,
        calling_role_key="licensing_negotiator",
        target_collection="grants",
        filters={"counterparty_id": auth.counterparty_id},
        session_context={"counterparty_id": auth.counterparty_id}
    )
    # Parse back to Pydantic models, then FOLD: the log is append-only, so a
    # revoked grant's original `granted` event is still present — permits()
    # must only ever see grants that are active after the fold (HOD-107).
    all_events = [GrantEvent(**g) for g in raw_grants]
    active_grants = active_grant_events(all_events)

    # 4. Resolve scope against lattice
    eval_result = permits(active_grants=active_grants, requested_scope=req.requested_scope)
    
    if eval_result.permitted:
        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            grant_id=eval_result.matching_grant_id or "unknown",
            counterparty_id=auth.counterparty_id,
            payload_hash=hashlib.sha256(await request.body()).hexdigest(),
            issued_at=datetime.now(timezone.utc),
            signature="SIG_RECEIPT"
        )

        granted_scope = next((g.scope for g in active_grants if g.grant_id == eval_result.matching_grant_id), None)
        licensable_set = [granted_scope.use_type, granted_scope.model_class] if granted_scope else []
            
        return LicenseResponse(
            permitted=True,
            licensable_set=licensable_set,
            explicit_exclusions=[],
            receipt=receipt,
            anomaly_detected=anomaly_detected,
            inspector_engine=armor_result.inspector_engine
        )
    else:
        return LicenseResponse(
            permitted=False,
            licensable_set=[],
            explicit_exclusions=[req.requested_scope.use_type, req.requested_scope.model_class],
            receipt=None,
            anomaly_detected=anomaly_detected,
            inspector_engine=armor_result.inspector_engine
        )

class NaturalScopeRequest(BaseModel):
    # Optional and NEVER trusted — see ScopeRequest.
    counterparty_id: Optional[str] = None
    request_text: str = Field(..., description="Natural-language license request from the counterparty")

class NaturalLicenseResponse(BaseModel):
    permitted: bool
    interpreted_scope: Optional[Scope] = None
    interpreter_model: str
    licensable_set: List[str]
    explicit_exclusions: List[str]
    receipt: Optional[Receipt] = None
    anomaly_detected: bool = False
    inspector_engine: str = "unknown"

@router.post("/api/v1/license/natural", response_model=NaturalLicenseResponse)
async def request_license_natural(req: NaturalScopeRequest, request: Request):
    """
    THE MODEL INTERPRETS INTENT. THE LATTICE DECIDES PERMISSION.

    Gemini structures the counterparty's natural-language request into a typed
    Scope; permits() decides against the lattice deterministically. The model's
    output cannot influence the permission decision except by producing a valid
    Scope — a malformed or out-of-vocabulary interpretation is rejected (422),
    never coerced.
    """
    from src.llm.scope_interpreter import ScopeInterpreter, ScopeInterpretationError
    from src.llm.vertex_gemini import GeminiUnavailableError

    # Authenticate first: identity comes from the verified credential, and the
    # model never sees a request that has not been attributed to a real caller.
    auth = await _authenticate_or_403(request, claimed_counterparty_id=req.counterparty_id,
                                      required_principal_type="counterparty")

    # Untrusted inbound buyer document: inspect post-extraction bytes (HOD-313).
    # Detection is logged and the request PROCEEDS under its original scope.
    armor_result = armor.inspect(req.request_text.encode("utf-8"))

    interpreter = ScopeInterpreter()
    try:
        interpreted = interpreter.interpret(req.request_text, valid_from=datetime.now(timezone.utc))
    except ScopeInterpretationError as e:
        raise HTTPException(status_code=422, detail=f"Interpretation rejected: {e}")
    except GeminiUnavailableError as e:
        raise HTTPException(status_code=503, detail=f"Interpreter unavailable: {e}")

    gateway = AgentGateway()
    raw_grants = gateway.read_collection(
        calling_sa=NEGOTIATOR_SA,
        calling_role_key="licensing_negotiator",
        target_collection="grants",
        filters={"counterparty_id": auth.counterparty_id},
        session_context={"counterparty_id": auth.counterparty_id}
    )
    # Fold before containment: permits() must only see active grants (HOD-107).
    active_grants = active_grant_events([GrantEvent(**g) for g in raw_grants])

    # The ONLY input the model contributed to this call is `interpreted`,
    # a schema-validated Scope. permits() is deterministic.
    eval_result = permits(active_grants=active_grants, requested_scope=interpreted)

    receipt = None
    licensable_set: List[str] = []
    exclusions: List[str] = []
    if eval_result.permitted:
        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            grant_id=eval_result.matching_grant_id or "unknown",
            counterparty_id=auth.counterparty_id,
            payload_hash=hashlib.sha256(await request.body()).hexdigest(),
            issued_at=datetime.now(timezone.utc),
            signature="SIG_RECEIPT"
        )
        granted_scope = next((g.scope for g in active_grants if g.grant_id == eval_result.matching_grant_id), None)
        licensable_set = [granted_scope.use_type, granted_scope.model_class] if granted_scope else []
    else:
        exclusions = [interpreted.use_type, interpreted.model_class]

    return NaturalLicenseResponse(
        permitted=eval_result.permitted,
        interpreted_scope=interpreted,
        interpreter_model=interpreter.model_id,
        licensable_set=licensable_set,
        explicit_exclusions=exclusions,
        receipt=receipt,
        anomaly_detected=armor_result.injection_detected,
        inspector_engine=armor_result.inspector_engine
    )

class RevokeRequest(BaseModel):
    work_id: str
    # `UseType`, not `str`. As a bare str this accepted "Training", "podcasting"
    # and "" and returned HTTP 200 with an empty cascade — a revocation that
    # reported success and did nothing, which is the worst possible answer for
    # an operation whose whole purpose is termination. The lattice has no entry
    # for an unknown use type, so `USE_TYPE_CONTAINMENT.get(x, {x})` degraded to
    # a single-element set that matched no grant. Now the request is refused
    # with HTTP 422 and the valid vocabulary, before any of that runs.
    revoked_use_type: UseType

@router.post("/api/v1/revoke", response_model=CascadeResult)
async def revoke_scope(req: RevokeRequest, request: Request):
    """
    Revocation is an ARTIST-side operation and requires an artist credential.

    This route shipped unauthenticated: anyone could revoke any work_id (work
    ids are published at /works), the response returned every affected
    counterparty's id and full negotiated scope, and because the log is
    append-only with no update/delete the writes are not undoable. It is the
    same defect class already fixed on /api/v1/license — the fix had not been
    carried across. See BUILD-LOG correction #6.

    A counterparty credential is explicitly NOT sufficient here: a buyer must
    not be able to terminate an artist's grants, including their own rivals'.

    Being *an* artist is also not sufficient: the caller must own THIS work.
    Authenticating the artist principal without checking ownership let any valid
    artist credential revoke any published `work_id` — latent under a single
    artist, a cross-tenant privilege escalation the moment there are two. The
    gate is a rights-custodian read of `works` (the propagator cannot read that
    collection by policy), comparing the work's `artist_id` to the authenticated
    identity before anything is delegated or appended.
    """
    auth = await _authenticate_or_403(request, claimed_counterparty_id=None,
                                      required_principal_type="artist")

    gateway = _get_gateway()
    _verify_work_ownership_or_403(gateway, work_id=req.work_id,
                                  authenticated_artist_id=auth.counterparty_id)

    propagator = RevocationPropagatorAgent(gateway=gateway, memory_bank_events=[])
    return propagator.execute_revocation_cascade(
        work_id=req.work_id, revoked_use_type=req.revoked_use_type
    )

class DelegationDrillRequest(BaseModel):
    work_id: str = "work-essay-001"
    revoked_use_type: UseType = "training"
    deadline_seconds: float = 1.0


@router.post("/api/v1/fleet/delegation_drill", response_model=Dict[str, Any])
async def fleet_delegation_drill(req: DelegationDrillRequest, request: Request):
    """
    Failure-tolerance drill on the DEPLOYED path (HOD-341, HOD-342).

    Runs the ADK delegation with the revocation propagator forced into a loop,
    so the Supervisor's deadline fires, the worker is quarantined and
    deregistered from the Registry, its task is rerouted to a standby that
    returns a stated partial result, and the request still completes.

    Structurally write-free: the looping worker never reaches its writes, and
    the degraded reroute issues no notices and appends no events by design. It
    reads fixture events, not live grants. Artist-credentialed all the same,
    because it is a mutating verb and every mutating route authenticates
    (tests/test_route_auth_coverage.py).
    """
    import json as _json
    import time as _time
    from pathlib import Path as _Path
    from src.supervisor.supervisor import Supervisor
    from src.fleet.adk_fleet import run_revocation_delegation

    await _authenticate_or_403(request, claimed_counterparty_id=None,
                               required_principal_type="artist")

    fixture = _Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo_grant_log.json"
    with open(fixture) as f:
        events = [GrantEvent(**e) for e in _json.load(f)["events"]]

    started = _time.perf_counter()
    result = run_revocation_delegation(
        counterparty_id="acme-intelligence-labs",
        work_id=req.work_id,
        revoked_use_type=req.revoked_use_type,
        fallback_events=events,
        supervisor=Supervisor(deadline_seconds=req.deadline_seconds),
        loop_forever=True,
    )
    elapsed_ms = (_time.perf_counter() - started) * 1000

    return {
        "measurement_surface": "deployed-over-network",
        "supervisor_deadline_seconds": req.deadline_seconds,
        "elapsed_ms": round(elapsed_ms, 2),
        "transcript": result["transcript"],
        "task_abandoned_events": result["task_abandoned_events"],
        "quarantine": result["quarantine"],
        "post_quarantine_discovery": result["post_quarantine_discovery"],
        "request_completed": result["quarantine"] is not None,
    }


class CompromisedAgentRequest(BaseModel):
    attack_type: str

# The demo session counterparty. A grant for this counterparty over one of the
# five registered corpus works is seeded by scripts/seed_demo_grant.py, so the
# properly scoped read returns real documents rather than an empty set.
DEMO_SESSION_COUNTERPARTY = "acme-intelligence-labs"
# The cross-counterparty attack targets a counterparty that genuinely exists in
# Firestore ('buyer-acme-2'), so the denial protects real data, not a phantom.
CROSS_COUNTERPARTY_TARGET = "buyer-acme-2"

@router.post("/api/v1/debug/compromised_agent_read", response_model=Dict[str, Any])
def debug_compromised_read(req: CompromisedAgentRequest):
    """
    Test endpoint for H7 to prove Gateway policy enforcement over the network.
    Simulates a compromised Licensing Negotiator attempting illegal reads.
    The only reads it can perform are (a) the properly scoped session read and
    (b) attempts that the Gateway denies — it cannot exfiltrate anything.
    """
    gateway = AgentGateway()

    try:
        if req.attack_type == "valid_read":
            docs = gateway.read_collection(
                calling_sa=NEGOTIATOR_SA,
                calling_role_key="licensing_negotiator",
                target_collection="grants",
                filters={"counterparty_id": DEMO_SESSION_COUNTERPARTY},
                session_context={"counterparty_id": DEMO_SESSION_COUNTERPARTY}
            )
            return {
                "status": "SUCCESS",
                "docs_returned": len(docs),
                "docs": jsonable_encoder(docs),
                "message": "Gateway permitted properly scoped read."
            }

        elif req.attack_type == "unfiltered":
            gateway.read_collection(
                calling_sa=NEGOTIATOR_SA,
                calling_role_key="licensing_negotiator",
                target_collection="grants",
                filters=None,
                session_context={"counterparty_id": DEMO_SESSION_COUNTERPARTY}
            )
        elif req.attack_type == "cross_counterparty":
            gateway.read_collection(
                calling_sa=NEGOTIATOR_SA,
                calling_role_key="licensing_negotiator",
                target_collection="grants",
                filters={"counterparty_id": CROSS_COUNTERPARTY_TARGET},
                session_context={"counterparty_id": DEMO_SESSION_COUNTERPARTY}
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown attack type")

        return {"status": "FAILED", "reason": "Gateway permitted the read when it should have denied it!"}
    except GatewayPolicyDenial as e:
        # The API response carries the same PolicyDenialEvent that was logged —
        # one denial, one reason, one source (HOD-312).
        return {
            "status": "DENIED",
            "error": str(e),
            "denial_event": e.denial.model_dump(mode="json")
        }
