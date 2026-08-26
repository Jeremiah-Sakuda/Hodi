import hashlib
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from src.schema.scope import Scope

EventKind = Literal["granted", "revoked", "expired", "superseded"]

def generate_deterministic_event_id(grant_id: str, step: int, attempt: int) -> str:
    """
    Generates a collision-resistant deterministic event_id.
    Uses colon delimiter formatting to prevent ('g1', 2, 3) vs ('g1', 23, '') collisions.
    """
    raw_payload = f"{grant_id}:{step}:{attempt}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

def reject_naive(value: Optional[datetime], field_name: str) -> Optional[datetime]:
    """A timestamp with no offset does not denote an instant (HOD-747).

    `resolve()` folds the log by sorting on `issued_at.astimezone(timezone.utc)`.
    On an AWARE datetime that converts. On a NAIVE one it does not raise — Python
    assumes the SERVER'S LOCAL time — so the same event log sorted on two
    machines produced two different orders and two different authorization
    answers:

        TZ=America/Los_Angeles -> active     (the buyer may train)
        TZ=UTC                 -> revoked    (the buyer may not)

    That is the `.isoformat()` string-sort defect wearing a different hat: an
    operation that silently succeeds on input it cannot actually interpret. The
    earlier fix corrected the comparison; it did not stop ambiguous input
    reaching it, so the same class returned through the door it left open.

    Rejecting at the boundary is the fix rather than defaulting to UTC. A default
    would make the fold deterministic while keeping the record wrong — the log is
    the artifact a counterparty is held to, and "we assumed UTC" is not something
    it should ever have to be read with. Firestore normalises to UTC on its own;
    every JSON-sourced log takes this path.
    """
    if value is not None and (value.tzinfo is None or value.tzinfo.utcoffset(value) is None):
        raise ValueError(
            f"{field_name} has no UTC offset ({value.isoformat()!r}). A naive timestamp "
            "does not denote an instant: the fold would sort it as server-local time and "
            "the same log would authorize differently on two machines. Attach an offset."
        )
    return value


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

    @field_validator("issued_at")
    @classmethod
    def _issued_at_must_denote_an_instant(cls, v):
        return reject_naive(v, "GrantEvent.issued_at")


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
