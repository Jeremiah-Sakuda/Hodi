import hashlib
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from src.schema.scope import Scope

EventKind = Literal["granted", "revoked", "expired", "superseded"]

def generate_deterministic_event_id(grant_id: str, step: int, attempt: int) -> str:
    """
    Generates a collision-resistant deterministic event_id.
    Uses colon delimiter formatting to prevent ('g1', 2, 3) vs ('g1', 23, '') collisions.
    """
    raw_payload = f"{grant_id}:{step}:{attempt}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

class GrantEvent(BaseModel):
    event_id: str
    grant_id: str
    work_id: str
    counterparty_id: str
    scope: Scope
    kind: EventKind
    supersedes: Optional[str] = None
    issued_at: datetime
    signature: str

class Receipt(BaseModel):
    receipt_id: str
    grant_id: str
    # The RESOURCE the decision was about (HOD-701). The authorization tuple is
    # principal × work × scope × time; a receipt that omits the work half-states
    # the decision it records. Optional only so receipts written before
    # 2026-08-14 still parse — every new receipt carries it.
    work_id: Optional[str] = None
    counterparty_id: str
    payload_hash: str
    issued_at: datetime
    signature: str
