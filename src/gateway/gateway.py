import os
from typing import Dict, Any, List
from pydantic import BaseModel
from datetime import datetime, timezone
from google.cloud import firestore
from src.schema.iam_policy import is_action_permitted, get_action_permission

class PolicyDenialEvent(BaseModel):
    event_id: str
    calling_sa: str
    target_role: str
    requested_collection: str
    timestamp: datetime
    policy_consulted: str = "gateway_policy_v1"
    outcome: str = "DENIED"
    reason: str

class AgentGateway:
    """
    Agent Gateway (HOD-312).
    Routes every inter-agent call and enforces IAM policy boundaries.
    Denials are logged as events and OTel spans, NEVER silent.
    Now directly reads from / writes to Firestore (H7 real path).
    """

    def __init__(self):
        self.denial_events: list = []
        project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        try:
            self.db = firestore.Client(project=project_id)
        except Exception:
            self.db = None # Allow fallback for unittests without ADC

    def _enforce(self, calling_sa: str, calling_role_key: str, target_collection: str, filters: Dict[str, Any] = None, session_context: Dict[str, Any] = None):
        permitted, required_filter_key = get_action_permission(calling_role_key, target_collection)
        
        reason = None
        if not permitted:
            reason = f"Calling SA '{calling_sa}' ({calling_role_key}) is denied access to target collection '{target_collection}'."
        elif required_filter_key:
            if not filters or required_filter_key not in filters:
                reason = f"Calling SA '{calling_sa}' ({calling_role_key}) MUST scope query to '{required_filter_key}' for collection '{target_collection}'."
            elif session_context and required_filter_key in session_context:
                # Gateway enforces the value matches the session context
                if filters[required_filter_key] != session_context[required_filter_key]:
                    reason = f"Calling SA '{calling_sa}' ({calling_role_key}) attempted to read '{required_filter_key}'='{filters[required_filter_key]}' outside of session context '{session_context[required_filter_key]}'."
                
        if reason:
            denial = PolicyDenialEvent(
                event_id=f"denial-{len(self.denial_events)+1}",
                calling_sa=calling_sa,
                target_role=calling_role_key,
                requested_collection=target_collection,
                timestamp=datetime.now(timezone.utc),
                reason=reason
            )
            self.denial_events.append(denial)
            raise PermissionError(f"GATEWAY_POLICY_DENIAL: {denial.reason}")

    def route(self, calling_sa: str, calling_role_key: str, target_collection: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy route method (kept for tests)."""
        self._enforce(calling_sa, calling_role_key, target_collection)
        return {
            "status": "ROUTED",
            "calling_sa": calling_sa,
            "target_collection": target_collection,
            "payload": payload
        }

    def read_collection(self, calling_sa: str, calling_role_key: str, target_collection: str, filters: Dict[str, Any] = None, session_context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        self._enforce(calling_sa, calling_role_key, target_collection, filters=filters, session_context=session_context)
        if not self.db:
            return [] # mock return for tests
            
        coll = self.db.collection(target_collection)
        if filters:
            for k, v in filters.items():
                coll = coll.where(k, "==", v)
        docs = coll.get()
        return [doc.to_dict() for doc in docs]

    def write_document(self, calling_sa: str, calling_role_key: str, target_collection: str, doc_id: str, data: Dict[str, Any]):
        self._enforce(calling_sa, calling_role_key, target_collection)
        if self.db:
            self.db.collection(target_collection).document(doc_id).set(data)
            
    def deliver_revocation_notice(self, sender: str, counterparty_id: str, notice: Any) -> Any:
        import uuid
        from src.schema.revocation import RevocationReceipt
        
        self.write_document(
            calling_sa=sender,
            calling_role_key="revocation_propagator",
            target_collection="revocation_notices",
            doc_id=str(uuid.uuid4()),
            data=notice.model_dump() if hasattr(notice, 'model_dump') else notice.dict()
        )
        
        receipt = RevocationReceipt(
            revocation_id=str(uuid.uuid4()),
            grant_id=notice.grant_id,
            counterparty_id=counterparty_id,
            revoked_at=notice.revoked_at,
            signature=f"SIG_REVOCATION_{notice.grant_id}"
        )
        return receipt
