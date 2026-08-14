import hashlib
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from src.schema.grant_event import GrantEvent

class RevocationNotice(BaseModel):
    grant_id: str = Field(..., description="The ID of the grant being revoked.")
    counterparty_id: str = Field(..., description="The opaque identifier for the buyer.")
    revoked_at: datetime = Field(..., description="Timestamp of revocation.")
    notice_text: str = Field(..., description="The text of the termination notice.")

class RevocationReceipt(BaseModel):
    revocation_id: str = Field(..., description="Unique receipt ID for the revocation.")
    grant_id: str = Field(..., description="The ID of the grant that was revoked.")
    counterparty_id: str = Field(..., description="The opaque identifier for the buyer.")
    revoked_at: datetime = Field(..., description="Timestamp of revocation.")
    signature: str = Field(..., description="Cryptographic signature of the revocation notice.")


class NoticeOutboxRecord(BaseModel):
    """
    The 'a notice is owed' half of a revocation, committed ATOMICALLY with the
    revoked GrantEvent (HOD-708). Delivery is a separate, retryable step whose
    completion marker is the notice document itself — a pending record is one
    whose deterministic notice id does not exist yet. Nothing here is ever
    updated: the record states an obligation, and the notice's existence
    states its discharge.
    """
    outbox_id: str
    operation_id: str
    grant_id: str
    work_id: str
    counterparty_id: str
    notice_text: str
    revoked_at: datetime
    created_at: datetime


def revocation_effect_id(operation_id: str, grant_id: str, effect: str) -> str:
    """
    Deterministic id for every document a revocation operation produces:
    effect ∈ {"revoked_event", "outbox", "notice", "receipt"}. A RETRY of the
    same operation derives the same ids, so replays collide on `create()`
    instead of duplicating — retrying a failed revocation cannot double its
    effects. Colon-delimited exactly as generate_deterministic_event_id, and
    for the same reason.
    """
    return hashlib.sha256(f"{operation_id}:{grant_id}:{effect}".encode("utf-8")).hexdigest()
