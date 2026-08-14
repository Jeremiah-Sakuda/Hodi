import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from src.schema.grant_event import GrantEvent, Receipt
from src.schema.revocation import (
    RevocationNotice, RevocationReceipt, NoticeOutboxRecord, revocation_effect_id,
)
from src.schema.signing import unsigned_placeholder, sign_pydantic
from src.schema.iam_policy import AGENT_SA_MAP
from src.schema.lattice import (
    USE_TYPE_CONTAINMENT, MODEL_CLASS_CONTAINMENT, use_type_derivation_chain,
    is_use_type_contained,
)
from src.resolve.resolver import resolve
from src.schema.iam_policy import AGENT_SA_MAP
from src.gateway.gateway import AgentGateway, DocumentAlreadyExists
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
    # The operation's idempotency key (HOD-708): retrying with the SAME
    # operation_id replays into deterministic ids and cannot double any
    # effect. A new operation_id is a new operation, and an already-revoked
    # grant is simply no longer active, so it is not affected again.
    operation_id: str
    revoked_use_type: str
    derived_scopes: List[str]
    structured_derivation: List[DerivedScope]
    affected_grants: List[AffectedGrant]
    issued_notices: List[RevocationReceipt]
    # How many terminate/outbox pairs were found already committed by a prior
    # run of this operation — nonzero exactly when this call was a retry.
    replayed_effects: int = 0

# Read from the policy module, never restated. This was a hand-written
# literal missing the "-sa" suffix, so every gateway call and denial event
# from the propagator logged an SA that does not exist — the audit record
# named a principal no IAM policy could confirm.
PROPAGATOR_SA = AGENT_SA_MAP["revocation_propagator"]["sa_email"]

class RevocationPropagatorAgent:
    """
    HOD-350: Computes affected grants and delegates revocation notice delivery.
    """
    def __init__(self, gateway: AgentGateway, memory_bank_events: List[GrantEvent] = None):
        self.gateway = gateway
        # Kept for backward compatibility with mock tests, though live path uses gateway
        self.memory_bank_events = memory_bank_events if memory_bank_events is not None else []

    # The conflict-boundary reads below go through the Gateway under this
    # agent's own service account, so the IAM tests exercise the SAME policy
    # path production uses. Four hardcoded "mock method for IAM test" stubs
    # previously stood here and returned canned values, which meant the IAM
    # tests asserted against the stubs rather than against the policy.
    def get_grants(self, work_id: str) -> Dict[str, Any]:
        """Paired positive: the propagator CAN read grants (its own domain)."""
        return {"status": "SUCCESS", "data": self.gateway.read_collection(
            calling_sa=PROPAGATOR_SA, calling_role_key="revocation_propagator",
            target_collection="grants", filters={"work_id": work_id})}

    def read_buyer_terms(self, counterparty_id: str) -> Dict[str, Any]:
        """Paired negative: the propagator CANNOT read buyer terms — denied by policy."""
        return self.gateway.read_collection(
            calling_sa=PROPAGATOR_SA, calling_role_key="revocation_propagator",
            target_collection="buyer_terms", filters={"counterparty_id": counterparty_id},
            session_context={"counterparty_id": counterparty_id})

    def read_artist_identity(self) -> Dict[str, Any]:
        """Paired negative: the propagator CANNOT hold artist identity — denied by policy."""
        return self.gateway.read_collection(
            calling_sa=PROPAGATOR_SA, calling_role_key="revocation_propagator",
            target_collection="artists")

    def execute_revocation_cascade(self, work_id: str, revoked_use_type: str,
                                   lease_id: str = None,
                                   operation_id: str = None) -> CascadeResult:
        """
        Revokes the specified use_type for a given work across all active grants.

        A grant is affected iff it PERMITS the revoked use — i.e. its held
        use_type contains `revoked_use_type` (the grant is at or above it in the
        lattice). Revoking `training` terminates a `training` grant; it does NOT
        terminate a `fine_tuning`-only grant, because that grant never permitted
        training and the artist did not revoke fine-tuning.

        This selection was BACKWARDS through 2026-08-10: it terminated grants
        whose held type was *contained by* the revoked type (its descendants),
        so revoking `training` destroyed every `fine_tuning`/`rag_retrieval`/
        `human_reference` grant — licenses for uses the artist never revoked —
        while revoking `fine_tuning` left a `training` grant able to fine-tune.
        12 of the 25 (held × revoked) cells were wrong (6 over, 6 under). The
        correct rule is the one `permits()` already encodes, reused here so
        there is one definition of "this scope permits that use". See the named
        finding in docs/FINDINGS.md and tests/test_revocation_reach.py.
        """
        # The operation's idempotency key (HOD-708). A caller retrying a failed
        # revocation passes the SAME operation_id and every effect id derives
        # from it; a fresh call without one is a fresh operation.
        operation_id = operation_id or f"revop-{uuid.uuid4()}"

        # `derived_scopes` describes what a terminated grant LOSES: the revoked
        # use and every narrower use it implies. It is the containment closure of
        # the revoked type — correct as the withdrawal description, and unrelated
        # to grant SELECTION, which was the bug. sorted() for stable rendering.
        derived_scopes = sorted(USE_TYPE_CONTAINMENT.get(revoked_use_type, {revoked_use_type}))
        
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
        
        # 1b. Derivation chain, walked from the LATTICE DATA — never branched on.
        # This was an if/elif ladder enumerating the chain per use-type, i.e. a
        # second source of truth for the partial order that lattice.py exists to
        # prevent. Adding a use-type would have silently produced an incomplete
        # cascade (HOD-104).
        structured_derivation = [
            DerivedScope(scope=scope, parent=parent, reason=reason)
            for scope, parent, reason in use_type_derivation_chain(revoked_use_type)
        ]
        
        affected_grants = []
        newly_committed = 0

        # PHASE 1 — TERMINATE + RECORD THE OBLIGATION, ATOMICALLY (HOD-708).
        # For each affected grant, the revoked GrantEvent and the notice-outbox
        # record are committed in ONE atomic batch under ids derived from the
        # operation: 'the grant is terminated' and 'a notice is owed' are one
        # fact, never two facts a crash can split. A retry of the same
        # operation derives the same ids and collides on create() — the
        # collision IS the idempotency signal, and it is skipped, not errored.
        for gid in sorted(unique_grant_ids):
            state = resolve(gid, events=events)
            if state.status == "active" and state.active_scope:
                # Affected iff the grant PERMITS the revoked use: the held type
                # contains it. Same predicate permits() uses, so a grant is
                # terminated exactly when it could have exercised the revoked use.
                if is_use_type_contained(state.active_scope.use_type, revoked_use_type):
                    affected_grants.append(AffectedGrant(
                        grant_id=gid,
                        counterparty_id=state.counterparty_id,
                        original_scope=state.active_scope
                    ))

                    # Notice text is Gemini-drafted and gated by RevocationLint;
                    # if drafting is unavailable or fails the lint, the linted
                    # deterministic template is used (src/llm/notice_drafter.py).
                    # Drafted BEFORE commit and stored IN the outbox record, so
                    # a retry delivers the same text that was committed, not a
                    # fresh drafting that might differ.
                    from src.llm.notice_drafter import NoticeDrafter
                    notice_text, _notice_source = NoticeDrafter().draft(
                        grant_id=gid, work_id=work_id, counterparty_id=state.counterparty_id
                    )
                    now = datetime.now(timezone.utc)
                    revoked_event_id = revocation_effect_id(operation_id, gid, "revoked_event")
                    outbox_id = revocation_effect_id(operation_id, gid, "outbox")
                    revoked_event = sign_pydantic(GrantEvent(
                        event_id=revoked_event_id,
                        grant_id=gid,
                        work_id=work_id,
                        counterparty_id=state.counterparty_id,
                        scope=state.active_scope,
                        kind="revoked",
                        issued_at=now,
                        signature=""
                    ), kind="revoked", reference=gid)
                    outbox_record = NoticeOutboxRecord(
                        outbox_id=outbox_id,
                        operation_id=operation_id,
                        grant_id=gid,
                        work_id=work_id,
                        counterparty_id=state.counterparty_id,
                        notice_text=notice_text,
                        revoked_at=now,
                        created_at=now,
                    )
                    try:
                        self.gateway.write_documents_atomic(
                            calling_sa=PROPAGATOR_SA,
                            calling_role_key="revocation_propagator",
                            writes=[
                                ("grants", revoked_event_id, revoked_event.model_dump()),
                                ("revocation_outbox", outbox_id, outbox_record.model_dump()),
                            ],
                            lease_id=lease_id,
                        )
                        newly_committed += 1
                        if raw_events == []:  # testing only: mirror into the in-memory bank
                            self.memory_bank_events.append(revoked_event)
                    except DocumentAlreadyExists:
                        # This operation already committed this grant's pair
                        # and the read raced it (stale snapshot). The
                        # obligation stands; delivery is phase 2's job.
                        pass

        # PHASE 2 — DISCHARGE THE OBLIGATIONS (retryable, at-least-once safe).
        issued_notices = self.deliver_pending_notices(operation_id=operation_id, lease_id=lease_id)

        # Each outbox row yields exactly one receipt, so obligations found
        # beyond those committed in THIS call are a prior attempt's — nonzero
        # exactly when this call was a retry. (On a retry the fold already
        # shows the grant revoked, so it is not re-affected; the leftover
        # obligation is what phase 2 discharges.)
        replayed = max(0, len(issued_notices) - newly_committed)

        return CascadeResult(
            operation_id=operation_id,
            revoked_use_type=revoked_use_type,
            derived_scopes=derived_scopes,
            structured_derivation=structured_derivation,
            affected_grants=affected_grants,
            issued_notices=issued_notices,
            replayed_effects=replayed,
        )

    def deliver_pending_notices(self, operation_id: str, lease_id: str = None) -> List[RevocationReceipt]:
        """
        Delivers every notice the operation's outbox owes (HOD-708 phase 2).

        Exactly-once BUSINESS effect over at-least-once EXECUTION: delivery
        writes the notice under a deterministic id, so a redelivery attempt
        collides and is skipped — the notice document's existence IS the
        discharge marker, itself append-only. The receipt is derived from the
        same operation, so a retry returns the same receipt identity rather
        than minting a second.
        """
        outbox_rows = self.gateway.read_collection(
            calling_sa=PROPAGATOR_SA,
            calling_role_key="revocation_propagator",
            target_collection="revocation_outbox",
            filters={"operation_id": operation_id},
        )
        receipts: List[RevocationReceipt] = []
        for row in sorted(outbox_rows, key=lambda r: r["grant_id"]):
            record = NoticeOutboxRecord(**row)
            notice = RevocationNotice(
                grant_id=record.grant_id,
                counterparty_id=record.counterparty_id,
                revoked_at=record.revoked_at,
                notice_text=record.notice_text,
            )
            notice_id = revocation_effect_id(operation_id, record.grant_id, "notice")
            try:
                self.gateway.write_document(
                    calling_sa=PROPAGATOR_SA,
                    calling_role_key="revocation_propagator",
                    target_collection="revocation_notices",
                    doc_id=notice_id,
                    data=notice.model_dump(),
                    lease_id=lease_id,
                )
            except DocumentAlreadyExists:
                pass  # already delivered by a prior attempt — the obligation is discharged
            receipts.append(sign_pydantic(RevocationReceipt(
                revocation_id=revocation_effect_id(operation_id, record.grant_id, "receipt"),
                grant_id=record.grant_id,
                counterparty_id=record.counterparty_id,
                revoked_at=record.revoked_at,
                signature="",
            ), kind="revocation_receipt", reference=record.grant_id))
        return receipts
