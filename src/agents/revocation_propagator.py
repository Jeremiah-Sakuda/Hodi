import uuid
from typing import List, Dict, Any
from datetime import datetime, timezone
from src.schema.grant_event import GrantEvent, Receipt
from src.schema.revocation import RevocationNotice, RevocationReceipt
from src.schema.signing import unsigned_placeholder
from src.schema.lattice import (
    USE_TYPE_CONTAINMENT, MODEL_CLASS_CONTAINMENT, use_type_derivation_chain,
    is_use_type_contained,
)
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
                                   lease_id: str = None) -> CascadeResult:
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
        issued_notices = []
        
        for gid in unique_grant_ids:
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
                        notice=notice,
                        lease_id=lease_id,
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
                        signature=unsigned_placeholder("revoked", gid)
                    )
                    self.gateway.write_document(
                        calling_sa=PROPAGATOR_SA,
                        calling_role_key="revocation_propagator",
                        target_collection="grants",
                        doc_id=new_event_id,
                        data=revoked_event.model_dump(),
                        lease_id=lease_id,
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
