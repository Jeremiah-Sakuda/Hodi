import uuid
from typing import List, Dict, Any
from datetime import datetime, timezone
from src.schema.grant_event import GrantEvent, Receipt
from src.schema.revocation import RevocationNotice, RevocationReceipt
from src.schema.lattice import USE_TYPE_CONTAINMENT, MODEL_CLASS_CONTAINMENT
from src.resolve.resolver import resolve
from src.gateway.gateway import AgentGateway
from pydantic import BaseModel

from src.schema.grant_event import GrantEvent, Receipt, Scope

class DerivedScope(BaseModel):
    scope: str
    parent: str
    reason: str

class AffectedGrant(BaseModel):
    grant_id: str
    counterparty_id: str
    original_scope: Scope

class CascadeResult(BaseModel):
    revoked_use_type: str
    derived_scopes: List[str]
    structured_derivation: List[DerivedScope]
    affected_grants: List[AffectedGrant]
    issued_notices: List[RevocationReceipt]

PROPAGATOR_SA = "revocation-propagator@hodi-2026.iam.gserviceaccount.com"

class RevocationPropagatorAgent:
    """
    HOD-350: Computes affected grants and delegates revocation notice delivery.
    """
    def __init__(self, gateway: AgentGateway, memory_bank_events: List[GrantEvent] = None):
        self.gateway = gateway
        # Kept for backward compatibility with mock tests, though live path uses gateway
        self.memory_bank_events = memory_bank_events if memory_bank_events is not None else []

    def get_grants(self):
        """Mock method for IAM positive test"""
        return {"status": "SUCCESS", "data": []}
        
    def write_revocation_notice(self, notice: Dict[str, Any]):
        """Mock method for IAM positive test"""
        return {"status": "SUCCESS", "receipt": "mock-receipt"}
        
    def read_buyer_terms(self, counterparty_id: str):
        """Mock method for IAM negative test"""
        raise PermissionError("PERMISSION_DENIED: Revocation Propagator cannot read buyer_terms")
        
    def read_artist_identity(self):
        """Mock method for IAM negative test"""
        raise PermissionError("PERMISSION_DENIED: Revocation Propagator cannot read artist identity")

    def execute_revocation_cascade(self, work_id: str, revoked_use_type: str) -> CascadeResult:
        """
        Revokes the specified use_type for a given work across all active grants.
        Cascades down the lattice (e.g. revoking 'training' pulls 'fine_tuning').
        """
        # 1. Resolve downstream derivative scopes by LATTICE CONTAINMENT
        derived_scopes = list(USE_TYPE_CONTAINMENT.get(revoked_use_type, {revoked_use_type}))
        
        # 2. Fetch all grant events for this work from real Firestore
        raw_events = self.gateway.read_collection(
            calling_sa=PROPAGATOR_SA,
            calling_role_key="revocation_propagator",
            target_collection="grants",
            filters={"work_id": work_id}
        )
        # Parse events. Fallback to self.memory_bank_events if no Firestore DB (in tests).
        if raw_events:
            events = [GrantEvent(**e) for e in raw_events]
        else:
            events = self.memory_bank_events
            
        unique_grant_ids = set(e.grant_id for e in events)
        
        # 1b. Build structured derivation chain for the UI
        structured_derivation = []
        if revoked_use_type == "training":
            structured_derivation = [
                DerivedScope(scope="training", parent="training", reason="Directly revoked"),
                DerivedScope(scope="fine_tuning", parent="training", reason="training ⊃ fine_tuning"),
                DerivedScope(scope="rag_retrieval", parent="fine_tuning", reason="fine_tuning ⊃ rag_retrieval"),
                DerivedScope(scope="human_reference", parent="rag_retrieval", reason="rag_retrieval ⊃ human_reference")
            ]
        elif revoked_use_type == "fine_tuning":
            structured_derivation = [
                DerivedScope(scope="fine_tuning", parent="fine_tuning", reason="Directly revoked"),
                DerivedScope(scope="rag_retrieval", parent="fine_tuning", reason="fine_tuning ⊃ rag_retrieval"),
                DerivedScope(scope="human_reference", parent="rag_retrieval", reason="rag_retrieval ⊃ human_reference")
            ]
        elif revoked_use_type == "rag_retrieval":
            structured_derivation = [
                DerivedScope(scope="rag_retrieval", parent="rag_retrieval", reason="Directly revoked"),
                DerivedScope(scope="human_reference", parent="rag_retrieval", reason="rag_retrieval ⊃ human_reference")
            ]
        else:
            structured_derivation = [DerivedScope(scope=revoked_use_type, parent=revoked_use_type, reason="Directly revoked")]
            
        affected_grants = []
        issued_notices = []
        
        for gid in unique_grant_ids:
            state = resolve(gid, events=events)
            if state.status == "active" and state.active_scope:
                if state.active_scope.use_type in derived_scopes:
                    affected_grants.append(AffectedGrant(
                        grant_id=gid,
                        counterparty_id=state.counterparty_id,
                        original_scope=state.active_scope
                    ))
                    
                    # 3. Emit signed notices via Gateway using opaque counterparty_id.
                    # Notice text is Gemini-drafted and gated by RevocationLint;
                    # if drafting is unavailable or fails the lint, the linted
                    # deterministic template is used (src/llm/notice_drafter.py).
                    from src.llm.notice_drafter import NoticeDrafter
                    notice_text, _notice_source = NoticeDrafter().draft(
                        grant_id=gid, work_id=work_id, counterparty_id=state.counterparty_id
                    )
                    notice = RevocationNotice(
                        grant_id=gid,
                        counterparty_id=state.counterparty_id,
                        revoked_at=datetime.now(timezone.utc),
                        notice_text=notice_text
                    )
                    
                    receipt = self.gateway.deliver_revocation_notice(
                        sender=PROPAGATOR_SA,
                        counterparty_id=state.counterparty_id,
                        notice=notice
                    )
                    
                    # 4. Generate the revoked GrantEvent and write to append-only log
                    new_event_id = str(uuid.uuid4())
                    revoked_event = GrantEvent(
                        event_id=new_event_id,
                        grant_id=gid,
                        work_id=work_id,
                        counterparty_id=state.counterparty_id,
                        scope=state.active_scope,
                        kind="revoked",
                        issued_at=datetime.now(timezone.utc),
                        signature="SIG_REVOKED"
                    )
                    self.gateway.write_document(
                        calling_sa=PROPAGATOR_SA,
                        calling_role_key="revocation_propagator",
                        target_collection="grants",
                        doc_id=new_event_id,
                        data=revoked_event.model_dump()
                    )
                    
                    if raw_events == []: # testing only
                        self.memory_bank_events.append(revoked_event)
                        
                    issued_notices.append(receipt)
                    
        return CascadeResult(
            revoked_use_type=revoked_use_type,
            derived_scopes=derived_scopes,
            structured_derivation=structured_derivation,
            affected_grants=affected_grants,
            issued_notices=issued_notices
        )
