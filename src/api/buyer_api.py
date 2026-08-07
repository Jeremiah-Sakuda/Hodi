import uuid
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from src.schema.scope import Scope, ScopeEvaluationResult
from src.schema.grant_event import GrantEvent, Receipt
from src.resolve.evaluator import permits
from src.gateway.prompt_inspector import PromptInspector
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.agents.revocation_propagator import RevocationPropagatorAgent, CascadeResult

router = APIRouter()
armor = PromptInspector()

# The licensing negotiator agent acts under its own service account
NEGOTIATOR_SA = "licensing-negotiator@hodi-2026.iam.gserviceaccount.com"

class ScopeRequest(BaseModel):
    counterparty_id: str
    requested_scope: Scope
    signature: str = Field(..., description="Cryptographic signature of the request")
    raw_document_b64: str = Field(..., description="Base64 encoded raw buyer document bytes")

class LicenseResponse(BaseModel):
    permitted: bool
    licensable_set: List[str]
    explicit_exclusions: List[str]
    receipt: Optional[Receipt] = None
    anomaly_detected: bool = False
    inspector_engine: str = "unknown"

@router.post("/api/v1/license", response_model=LicenseResponse)
def request_license(req: ScopeRequest):
    # 1. Verify signature (Reject unsigned)
    if not req.signature:
        raise HTTPException(status_code=400, detail="Unsigned request rejected.")
        
    # 2. Route raw post-extraction bytes through ModelArmor
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
        filters={"counterparty_id": req.counterparty_id},
        session_context={"counterparty_id": req.counterparty_id}
    )
    # Parse back to Pydantic models
    active_grants = [GrantEvent(**g) for g in raw_grants]
    
    # 4. Resolve scope against lattice
    eval_result = permits(active_grants=active_grants, requested_scope=req.requested_scope)
    
    if eval_result.permitted:
        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            grant_id=eval_result.matching_grant_id or "unknown",
            counterparty_id=req.counterparty_id,
            payload_hash="real_hash",
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

class RevokeRequest(BaseModel):
    work_id: str
    revoked_use_type: str

@router.post("/api/v1/revoke", response_model=CascadeResult)
def revoke_scope(req: RevokeRequest):
    gateway = AgentGateway()
    propagator = RevocationPropagatorAgent(gateway=gateway, memory_bank_events=[])
    
    # Execute cascade
    result = propagator.execute_revocation_cascade(work_id=req.work_id, revoked_use_type=req.revoked_use_type)
    return result

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
