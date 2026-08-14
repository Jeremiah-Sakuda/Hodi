"""
src/memory/memory_bank.py — Memory Bank (HOD-331, HOD-710).

Until 2026-08-14 this class stored events in a Python list and its
docstring said "surviving cold starts and container restarts" — a claim
carried entirely by OTHER code (the Firestore grant log read through the
gateway), while the class under the name died with the process. The
mechanism now matches the claim: the bank folds over a pluggable
append-only store — Firestore live, in-memory offline — so cold-start
re-hydration is a property of THIS class, provable by constructing a
fresh instance against the same store and getting an identical fold.

resolve() remains the single read path for grant state; the bank is a
thin owner of "which store, which collection," never a second fold.
"""

from typing import List, Optional
from datetime import datetime

from src.schema.grant_event import GrantEvent
from src.resolve.resolver import resolve, active_grant_events, CurrentGrantState
from src.memory.event_store import InMemoryEventStore, default_event_store


class MemoryBank:
    def __init__(self, store=None, collection: str = "grants"):
        self._store = store if store is not None else default_event_store()
        self._collection = collection

    def append_event(self, event: GrantEvent) -> None:
        """Create-only append; a duplicate event_id raises, never overwrites."""
        self._store.append(self._collection, event.event_id, event.model_dump(mode="json"))

    def events(self, grant_id: Optional[str] = None) -> List[GrantEvent]:
        filters = {"grant_id": grant_id} if grant_id else None
        return [GrantEvent(**row) for row in self._store.read(self._collection, filters=filters)]

    def resolve_state(self, grant_id: str, at: Optional[datetime] = None) -> CurrentGrantState:
        """Pure fold re-hydration over the DURABLE log — identical from a
        fresh instance, which is the HOD-331/HOD-710 property."""
        return resolve(grant_id, at=at, events=self.events(grant_id))

    def active_grants(self, at: Optional[datetime] = None) -> List[GrantEvent]:
        return active_grant_events(self.events(), at=at)
