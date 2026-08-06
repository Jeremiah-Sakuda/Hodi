from typing import List, Optional, Dict, Any
from datetime import datetime
from src.schema.grant_event import GrantEvent
from src.resolve.resolver import resolve, CurrentGrantState

class MemoryBank:
    """
    Memory Bank (HOD-331).
    Long-lived grant, scope, and revocation state surviving cold starts and container restarts.
    State is deterministically re-hydrated via resolve(grant_id, at=t).
    """

    def __init__(self):
        self._events_log: List[GrantEvent] = []

    def append_event(self, event: GrantEvent):
        """Appends event to long-lived Memory Bank log."""
        self._events_log.append(event)

    def resolve_state(self, grant_id: str, at: Optional[datetime] = None) -> CurrentGrantState:
        """Pure fold re-hydration over long-lived Memory Bank log."""
        return resolve(grant_id, at=at, events=self._events_log)
