import os
import json
import uuid
import subprocess
from typing import TYPE_CHECKING, Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from google.cloud import firestore
from google.api_core import exceptions as gcloud_exceptions
from src.schema.iam_policy import is_action_permitted, get_action_permission, AGENT_SA_MAP
from src.schema.signing import unsigned_placeholder, sign_pydantic

if TYPE_CHECKING:
    from src.supervisor.lease import LeaseLedger

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


class DocumentAlreadyExists(Exception):
    """
    A `create()` collided with an existing document id — the SAME answer on
    the live path (Firestore AlreadyExists) and offline (the in-memory write
    sink), so idempotent-replay handling can be written once and mean the
    same thing in both. For deterministic, operation-derived ids a collision
    is the IDEMPOTENCY signal: this effect has already been committed.
    """
    def __init__(self, collection: str, doc_id: str):
        self.collection = collection
        self.doc_id = doc_id
        super().__init__(f"Document '{doc_id}' already exists in '{collection}'.")

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

    def __init__(self, offline_reads: Optional[Dict[str, List[dict]]] = None,
                 lease_ledger: Optional["LeaseLedger"] = None):
        self.denial_events: list = []
        project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        self.db = _build_firestore_client(project_id)
        # Documents served to read_collection when there is no live Firestore
        # (HODI_OFFLINE / tests), keyed by collection. Policy enforcement still
        # runs first, so an offline read is denied exactly when a live one is —
        # this only supplies the data a permitted read would have returned.
        self._offline_reads: Dict[str, List[dict]] = offline_reads or {}
        # Execution-lease enforcement (HOD-707). When a ledger is attached the
        # gateway is operating in a SUPERVISED context, and every side-effecting
        # write must present a lease that is valid AT THE MOMENT OF THE WRITE.
        # Fail closed: with a ledger attached, a write with no lease at all is
        # a violation, not a legacy path — a missing lease and a revoked lease
        # are the same answer, exactly as a missing session context is on reads.
        self._lease_ledger = lease_ledger
        # Offline write sink. Mirrors the LIVE `.create()` semantics — a
        # duplicate id RAISES (DocumentAlreadyExists) instead of silently
        # no-opping — because the idempotency machinery (HOD-708) leans on
        # exactly that collision, and an offline path that cannot collide
        # would make every idempotency test a test of nothing.
        self._offline_writes: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _enforce(self, calling_sa: str, calling_role_key: str, target_collection: str, filters: Dict[str, Any] = None, session_context: Dict[str, Any] = None):
        permitted, required_filter_key = get_action_permission(calling_role_key, target_collection)

        reason = None

        # The claimed SA must be the one the policy declares for the claimed
        # role. Until now `calling_sa` was passed alongside `calling_role_key`,
        # never compared to it, and used only in log text — so the two could
        # disagree indefinitely, and they DID: the propagator passed
        # "revocation-propagator@" while the policy declares
        # "revocation-propagator-sa@", meaning every denial event it produced
        # named a principal that does not exist in IAM. An audit record whose
        # subject cannot be resolved is not an audit record.
        #
        # STATED PRECISELY, because this is the project's most over-claimable
        # boundary: this binds the pair, it does NOT authenticate it. Both
        # values still arrive from the caller, so in-process code could present
        # a matching pair for a role it should not hold. Real non-forgeability
        # requires the role to be derived from a verified workload credential
        # (per-domain service, OIDC identity token, audience check) — that is
        # the four-service split, which remains the disclosed next step. What
        # this closes is silent drift between the identity we enforce and the
        # identity we record.
        declared = AGENT_SA_MAP.get(calling_role_key, {}).get("sa_email")
        if declared and calling_sa != declared:
            reason = (f"Calling SA '{calling_sa}' does not match the service account the policy "
                      f"declares for role '{calling_role_key}' ('{declared}'). The identity "
                      "enforced and the identity recorded must be the same principal.")

        if reason:
            pass  # identity mismatch already decided this call
        elif not permitted:
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

    def log_containment_denial(self, counterparty_id: str, freeze_id: str,
                               incident_id: str) -> PolicyDenialEvent:
        """
        Records a licensing request refused because the principal's
        negotiation is frozen by a standing consent incident (HOD-705).
        Same structured event, same log, same non-silence as every denial.
        """
        denial = PolicyDenialEvent(
            event_id=f"denial-{uuid.uuid4()}",
            calling_sa="api-layer (containment gate)",
            target_role="licensing_negotiator",
            requested_collection="grants",
            attempted_filters={"counterparty_id": counterparty_id},
            session_context={"freeze_id": freeze_id, "incident_id": incident_id},
            timestamp=datetime.now(timezone.utc),
            policy_consulted="incident_containment_v1",
            reason=(f"Negotiation for counterparty '{counterparty_id}' is frozen by "
                    f"consent incident '{incident_id}' (freeze '{freeze_id}'). "
                    "Licensing is refused while the incident record stands."),
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
            # Offline: serve injected documents plus anything written through
            # this gateway instance (a read after a write must see the write,
            # exactly as it would live), applying the same equality filters a
            # live query would.
            docs = list(self._offline_reads.get(target_collection, []))
            docs += list(self._offline_writes.get(target_collection, {}).values())
            if filters:
                docs = [d for d in docs if all(d.get(k) == v for k, v in filters.items())]
            return docs

        coll = self.db.collection(target_collection)
        if filters:
            for k, v in filters.items():
                coll = coll.where(k, "==", v)
        docs = coll.get()
        return [doc.to_dict() for doc in docs]

    def _enforce_lease(self, calling_sa: str, calling_role_key: str,
                       target_collection: str, lease_id: Optional[str]) -> None:
        """
        Immediately-before-commit lease check (HOD-707). Only active when a
        ledger is attached (supervised context). The check happens HERE, at the
        gateway, because the worker whose lease was revoked is exactly the
        worker whose cooperation cannot be assumed — the same reasoning as
        TaskAbandoned being written by the supervisor.
        """
        if self._lease_ledger is None:
            return
        state = self._lease_ledger.state(lease_id) if lease_id else None
        if state is not None and state.status == "active":
            return
        if lease_id is None:
            reason = (f"Calling SA '{calling_sa}' ({calling_role_key}) attempted a supervised write to "
                      f"'{target_collection}' with NO execution lease. In a supervised context a write "
                      f"without a lease is a violation, not a legacy path.")
        else:
            reason = (f"Calling SA '{calling_sa}' ({calling_role_key}) attempted a write to "
                      f"'{target_collection}' under a stale execution lease '{lease_id}' "
                      f"(status: {state.status}"
                      + (f", revoked: {state.revoked_reason}" if state.revoked_reason else "")
                      + "). The supervisor has already routed around this worker; its commit is refused.")
        denial = PolicyDenialEvent(
            event_id=f"denial-{uuid.uuid4()}",
            calling_sa=calling_sa,
            target_role=calling_role_key,
            requested_collection=target_collection,
            attempted_filters={"lease_id": lease_id},
            session_context={"lease_status": state.status if state else "absent"},
            timestamp=datetime.now(timezone.utc),
            policy_consulted="execution_lease_v1",
            reason=reason,
        )
        self.denial_events.append(denial)
        _emit_denial_log(denial)
        raise GatewayPolicyDenial(denial)

    def write_document(self, calling_sa: str, calling_role_key: str, target_collection: str,
                       doc_id: str, data: Dict[str, Any], lease_id: Optional[str] = None):
        self._enforce(calling_sa, calling_role_key, target_collection)
        self._enforce_lease(calling_sa, calling_role_key, target_collection, lease_id)
        if self.db:
            # `.create()`, not `.set()`. `.set()` is an UPSERT — it silently
            # overwrites an existing document — and Firestore's IAM backend
            # classifies it as needing `datastore.entities.update`, the exact
            # permission the runtime identity is denied so that history cannot
            # be rewritten. `.create()` is a true append: it needs only
            # `datastore.entities.create`, and it RAISES on a duplicate id
            # rather than overwriting. For an append-only event log with unique
            # event ids that is the correct and stronger semantics — a colliding
            # id is a bug that should fail loudly, never a silent replace. For
            # OPERATION-DERIVED deterministic ids (HOD-708) the collision is
            # the idempotency signal, surfaced as DocumentAlreadyExists.
            try:
                self.db.collection(target_collection).document(doc_id).create(data)
            except gcloud_exceptions.AlreadyExists:
                raise DocumentAlreadyExists(target_collection, doc_id)
        else:
            bucket = self._offline_writes.setdefault(target_collection, {})
            if doc_id in bucket:
                raise DocumentAlreadyExists(target_collection, doc_id)
            bucket[doc_id] = dict(data)

    def write_documents_atomic(self, calling_sa: str, calling_role_key: str,
                               writes: List[tuple], lease_id: Optional[str] = None):
        """
        Creates several documents ATOMICALLY — all or none (HOD-708).

        `writes` is a list of (collection, doc_id, data). The revocation
        cascade commits the revoked GrantEvent and its notice-outbox record
        through here, so 'the grant is terminated' and 'a notice is owed' are
        one fact, never two facts that a crash can split. Live this is a
        Firestore WriteBatch of `.create()`s (atomic, and AlreadyExists fails
        the whole batch); offline every id is checked free before anything is
        written. Policy and lease are enforced per target collection BEFORE
        any write — a denial on any one write denies the batch.
        """
        for collection, _doc_id, _data in writes:
            self._enforce(calling_sa, calling_role_key, collection)
            self._enforce_lease(calling_sa, calling_role_key, collection, lease_id)

        if self.db:
            batch = self.db.batch()
            for collection, doc_id, data in writes:
                batch.create(self.db.collection(collection).document(doc_id), data)
            try:
                batch.commit()
            except gcloud_exceptions.AlreadyExists:
                first = writes[0]
                raise DocumentAlreadyExists(first[0], first[1])
        else:
            for collection, doc_id, _data in writes:
                if doc_id in self._offline_writes.get(collection, {}):
                    raise DocumentAlreadyExists(collection, doc_id)
            for collection, doc_id, data in writes:
                self._offline_writes.setdefault(collection, {})[doc_id] = dict(data)

    def submit_assertion(self, calling_sa: str, calling_role_key: str, assertion) -> Any:
        """
        The epistemic gate (HOD-703). An assertion enters the fleet's record
        only if the submitting ROLE holds authority for its CLASS — the same
        fail-closed shape as collection policy, consulted from
        ASSERTION_AUTHORITY (data, not branching), refused as the same
        structured PolicyDenialEvent.

        Note what never reaches this check: a claim with no assertion class —
        MODEL_TRAINED_ON_WORK above all — dies at the TypedAssertion schema
        before any code runs. The gate governs who may say the SAYABLE; the
        schema keeps the unsayable unsayable.
        """
        from src.schema.assertion_authority import may_assert
        if not may_assert(calling_role_key, assertion.assertion_class):
            denial = PolicyDenialEvent(
                event_id=f"denial-{uuid.uuid4()}",
                calling_sa=calling_sa,
                target_role=calling_role_key,
                requested_collection="incident_assertions",
                attempted_filters={"assertion_class": assertion.assertion_class},
                session_context={"asserted_by_role": assertion.asserted_by_role},
                timestamp=datetime.now(timezone.utc),
                policy_consulted="assertion_authority_v1",
                reason=(f"Role '{calling_role_key}' lacks authority for assertion class "
                        f"'{assertion.assertion_class}'. Who may claim what is policy, and "
                        "this claim is outside this role's epistemic position."),
            )
            self.denial_events.append(denial)
            _emit_denial_log(denial)
            raise GatewayPolicyDenial(denial)
        return assertion

    def deliver_revocation_notice(self, sender: str, counterparty_id: str, notice: Any,
                                  lease_id: Optional[str] = None) -> Any:
        from src.schema.revocation import RevocationReceipt

        self.write_document(
            calling_sa=sender,
            calling_role_key="revocation_propagator",
            target_collection="revocation_notices",
            doc_id=str(uuid.uuid4()),
            data=notice.model_dump() if hasattr(notice, 'model_dump') else notice.dict(),
            lease_id=lease_id,
        )

        receipt = sign_pydantic(RevocationReceipt(
            revocation_id=str(uuid.uuid4()),
            grant_id=notice.grant_id,
            counterparty_id=counterparty_id,
            revoked_at=notice.revoked_at,
            signature=""
        ), kind="revocation_receipt", reference=notice.grant_id)
        return receipt
