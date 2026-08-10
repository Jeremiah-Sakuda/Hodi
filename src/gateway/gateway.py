import os
import json
import uuid
import subprocess
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from google.cloud import firestore
from src.schema.iam_policy import is_action_permitted, get_action_permission

class PolicyDenialEvent(BaseModel):
    event_type: str = "PolicyDenialEvent"
    event_id: str
    calling_sa: str
    target_role: str
    requested_collection: str
    attempted_filters: Optional[Dict[str, Any]] = None
    session_context: Optional[Dict[str, Any]] = None
    timestamp: datetime
    policy_consulted: str = "gateway_policy_v1"
    outcome: str = "DENIED"
    reason: str

class GatewayPolicyDenial(PermissionError):
    """
    Raised on every gateway policy denial (HOD-312).
    Carries the structured PolicyDenialEvent so the API response and the log
    entry state the SAME reason from the SAME source — one denial, one record.
    """
    def __init__(self, denial: PolicyDenialEvent):
        self.denial = denial
        super().__init__(f"GATEWAY_POLICY_DENIAL: {denial.reason}")

def _emit_denial_log(denial: PolicyDenialEvent) -> None:
    """
    Emits the denial as one pure-JSON line on stdout. Cloud Run ingests each
    JSON stdout line as a structured Cloud Logging entry (jsonPayload), so the
    denial is queryable by field — never a stack trace, never silent.
    """
    entry = {"severity": "WARNING", "message": f"GATEWAY_POLICY_DENIAL: {denial.reason}"}
    entry.update(json.loads(denial.model_dump_json()))
    print(json.dumps(entry), flush=True)

def _build_firestore_client(project_id: str):
    """ADC first; falls back to the gcloud CLI token for local dev shells without ADC.
    HODI_OFFLINE=1 forces no client — used by `make demo` so the credential-free
    path is genuinely credential-free even on a machine that has credentials."""
    if os.environ.get("HODI_OFFLINE") == "1":
        return None
    try:
        return firestore.Client(project=project_id)
    except Exception:
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
            ).decode("utf-8").strip()
            from google.oauth2 import credentials as oauth2_credentials
            return firestore.Client(project=project_id, credentials=oauth2_credentials.Credentials(token))
        except Exception:
            return None  # Allow fallback for unittests without any credentials

class AgentGateway:
    """
    Agent Gateway (HOD-312).
    Routes every inter-agent call and enforces IAM policy boundaries.
    Denials are logged as structured PolicyDenialEvents and OTel spans, NEVER silent
    and never as an unhandled stack trace.
    Reads from / writes to Firestore directly (H7 real path).
    """

    def __init__(self):
        self.denial_events: list = []
        project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        self.db = _build_firestore_client(project_id)

    def _enforce(self, calling_sa: str, calling_role_key: str, target_collection: str, filters: Dict[str, Any] = None, session_context: Dict[str, Any] = None):
        permitted, required_filter_key = get_action_permission(calling_role_key, target_collection)

        reason = None
        if not permitted:
            reason = f"Calling SA '{calling_sa}' ({calling_role_key}) is denied access to target collection '{target_collection}'."
        elif required_filter_key:
            # FAIL CLOSED. A missing session context is a denial, not a skip.
            #
            # This previously read `elif session_context and required_filter_key
            # in session_context:` — the comparison only happened when the CALLER
            # chose to supply context, so a call that simply omitted it was
            # permitted. That is the same shape as both live auth defects
            # (BUILD-LOG corrections #5 and #6): a check whose enforcement depends
            # on the caller cooperating. The session scope is the boundary, so
            # its absence cannot be the permissive case.
            if not filters or required_filter_key not in filters:
                reason = f"Calling SA '{calling_sa}' ({calling_role_key}) MUST scope query to '{required_filter_key}' for collection '{target_collection}'."
            elif not session_context or required_filter_key not in session_context:
                reason = (f"Calling SA '{calling_sa}' ({calling_role_key}) supplied no session context for "
                          f"'{required_filter_key}' on collection '{target_collection}'. A session-scoped "
                          f"collection cannot be read without the session it is scoped to.")
            elif filters[required_filter_key] != session_context[required_filter_key]:
                reason = f"Calling SA '{calling_sa}' ({calling_role_key}) attempted to read '{required_filter_key}'='{filters[required_filter_key]}' outside of session context '{session_context[required_filter_key]}'."

        if reason:
            denial = PolicyDenialEvent(
                event_id=f"denial-{uuid.uuid4()}",
                calling_sa=calling_sa,
                target_role=calling_role_key,
                requested_collection=target_collection,
                attempted_filters=filters,
                session_context=session_context,
                timestamp=datetime.now(timezone.utc),
                reason=reason
            )
            self.denial_events.append(denial)
            _emit_denial_log(denial)
            raise GatewayPolicyDenial(denial)

    def log_identity_claim_denial(self, calling_sa: str, authenticated_counterparty_id: str,
                                  claimed_counterparty_id: str, key_id: str) -> PolicyDenialEvent:
        """
        Records a rejected cross-buyer identity claim: a caller authenticated as
        one counterparty asked for another's data. Logged as the same structured
        PolicyDenialEvent as any other denial — never a silent 403.
        """
        denial = PolicyDenialEvent(
            event_id=f"denial-{uuid.uuid4()}",
            calling_sa=calling_sa,
            target_role="licensing_negotiator",
            requested_collection="grants",
            attempted_filters={"counterparty_id": claimed_counterparty_id},
            session_context={"counterparty_id": authenticated_counterparty_id, "key_id": key_id},
            timestamp=datetime.now(timezone.utc),
            policy_consulted="request_authentication_v1",
            reason=(f"Credential '{key_id}' is bound to counterparty "
                    f"'{authenticated_counterparty_id}' and cannot act for "
                    f"'{claimed_counterparty_id}'."),
        )
        self.denial_events.append(denial)
        _emit_denial_log(denial)
        return denial

    def log_principal_type_denial(self, calling_sa: str, key_id: str, principal_type: str,
                                  required_principal_type: str, operation: str) -> PolicyDenialEvent:
        """
        Records a credential used for an operation its principal type may not
        perform — e.g. a buyer's credential attempting a revocation. Logged as
        the same structured event as any other denial.
        """
        denial = PolicyDenialEvent(
            event_id=f"denial-{uuid.uuid4()}",
            calling_sa=calling_sa,
            target_role=required_principal_type,
            requested_collection=operation,
            attempted_filters={"principal_type": principal_type},
            session_context={"key_id": key_id, "principal_type": principal_type},
            timestamp=datetime.now(timezone.utc),
            policy_consulted="principal_type_policy_v1",
            reason=(f"Credential '{key_id}' is a '{principal_type}' principal and cannot perform "
                    f"'{operation}', which requires a '{required_principal_type}' principal."),
        )
        self.denial_events.append(denial)
        _emit_denial_log(denial)
        return denial

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
            # `.create()`, not `.set()`. `.set()` is an UPSERT — it silently
            # overwrites an existing document — and Firestore's IAM backend
            # classifies it as needing `datastore.entities.update`, the exact
            # permission the runtime identity is denied so that history cannot
            # be rewritten. `.create()` is a true append: it needs only
            # `datastore.entities.create`, and it RAISES on a duplicate id
            # rather than overwriting. For an append-only event log with unique
            # event ids that is the correct and stronger semantics — a colliding
            # id is a bug that should fail loudly, never a silent replace.
            self.db.collection(target_collection).document(doc_id).create(data)

    def deliver_revocation_notice(self, sender: str, counterparty_id: str, notice: Any) -> Any:
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
