from typing import List, Optional, Dict
from datetime import datetime, timezone
from pydantic import BaseModel
from src.schema.grant_event import GrantEvent, Scope

class CurrentGrantState(BaseModel):
    grant_id: str
    work_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    active_scope: Optional[Scope] = None
    status: str = "nonexistent"  # "active", "revoked", "superseded", "nonexistent"
    superseded_by: Optional[str] = None
    last_event_id: Optional[str] = None
    history_events: List[GrantEvent] = []

def resolve(
    grant_id: str,
    at: Optional[datetime] = None,
    events: Optional[List[GrantEvent]] = None
) -> CurrentGrantState:
    """
    resolve(grant_id, at=t) — The single read path for grant state (HOD-103, HOD-107).
    
    Executes a pure fold over append-only grant events up to timestamp `at`.
    Current state and historical state are the same fold evaluated at different timestamps.
    """
    if events is None:
        events = []

    # 1. Filter events matching grant_id and issued_at <= at
    matching_events = []
    for ev in events:
        if ev.grant_id == grant_id:
            if at is None or ev.issued_at <= at:
                matching_events.append(ev)

    # 2. Sort deterministically by (issued_at, event_id)
    # NOTE: Sorting by (issued_at, event_id) breaks ties on event_id deterministically.
    # This is required for HOD-103 byte-stability replay guarantee; changing it breaks historical reproducibility.
    matching_events.sort(key=lambda e: (e.issued_at.isoformat(), e.event_id))

    # 3. Pure fold over event history
    state = CurrentGrantState(grant_id=grant_id)
    state.history_events = list(matching_events)

    for ev in matching_events:
        state.work_id = ev.work_id
        state.counterparty_id = ev.counterparty_id
        state.last_event_id = ev.event_id

        if ev.kind == "granted":
            state.active_scope = ev.scope
            state.status = "active"
            state.superseded_by = None
        elif ev.kind == "revoked":
            state.active_scope = None
            state.status = "revoked"
        elif ev.kind == "superseded":
            # A superseded grant is NOT active. It is history.
            #
            # This previously returned the superseded scope as `active_scope`,
            # so `resolve()` said "superseded" while handing back a live scope,
            # `active_grant_events()` (correctly) returned nothing, and
            # `permits()` (incorrectly) accepted the raw event — three
            # components, three answers. The event stays in the log, readable
            # and struck through; it simply does not grant anything.
            state.active_scope = None
            state.status = "superseded"
            state.superseded_by = ev.supersedes
        elif ev.kind == "expired":
            state.active_scope = None
            state.status = "expired"

    return state


def active_grant_events(events: List[GrantEvent], at: Optional[datetime] = None) -> List[GrantEvent]:
    """
    Folds an append-only event list and returns, for each grant that is ACTIVE
    at `at`, the event that defines its current scope.

    permits() takes ACTIVE grants, not raw events. In an append-only log a
    revoked grant's original `granted` event is still present — passing raw
    events to permits() would let a revoked grant keep permitting requests.
    Every caller that reads events from the log MUST fold through here first;
    resolve() remains the single read path and this is a thin projection of it.
    """
    result: List[GrantEvent] = []
    for gid in sorted({e.grant_id for e in events}):
        state = resolve(gid, at=at, events=[e for e in events if e.grant_id == gid])
        if state.status == "active" and state.active_scope is not None:
            defining = [e for e in state.history_events if e.kind in ("granted", "superseded")][-1]
            result.append(defining)
    return result
