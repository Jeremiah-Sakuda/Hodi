"""
src/memory/event_store.py — the pluggable append-only event store
(HOD-709, HOD-710).

The Memory Bank and the Agent Registry both claimed durability their
mechanisms did not have: each held a Python dict that died with the
process, while the durable state actually lived elsewhere (Firestore,
through the gateway) or nowhere. The claim and the mechanism now meet in
one place: both fold over THIS store, which is Firestore on the live path
and an in-memory twin offline — with the SAME create-only collision
semantics, so offline tests exercise the discipline the live path
enforces, not a friendlier one.

This is control-plane storage (who is published, what the fleet
remembers), not agent-domain data — it deliberately does not pass through
the conflict-wall gateway, and nothing here may ever hold buyer terms,
artist identity, or evidence. Domain data keeps its single read path:
resolve() over the gateway-mediated grant log.
"""

import os
from typing import Any, Dict, List, Optional

from google.api_core import exceptions as gcloud_exceptions


class DuplicateEventId(Exception):
    """A create() collided — the store is append-only and never overwrites."""
    def __init__(self, collection: str, doc_id: str):
        self.collection = collection
        self.doc_id = doc_id
        super().__init__(f"Event '{doc_id}' already exists in '{collection}'.")


class InMemoryEventStore:
    """
    The offline twin. Same interface, same collision behavior as Firestore
    `.create()`. A store that cannot collide would make append-only tests
    tests of nothing.
    """

    def __init__(self):
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def append(self, collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        bucket = self._collections.setdefault(collection, {})
        if doc_id in bucket:
            raise DuplicateEventId(collection, doc_id)
        bucket[doc_id] = dict(data)

    def read(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        docs = list(self._collections.get(collection, {}).values())
        if filters:
            docs = [d for d in docs if all(d.get(k) == v for k, v in filters.items())]
        return [dict(d) for d in docs]


class FirestoreEventStore:
    """
    The live store: create-only appends, equality-filtered reads. Requires
    ambient credentials; nothing constructs one under HODI_OFFLINE=1.
    """

    def __init__(self, project_id: Optional[str] = None, client=None):
        if client is not None:
            self._db = client
        else:
            if os.environ.get("HODI_OFFLINE") == "1":
                raise RuntimeError(
                    "FirestoreEventStore constructed under HODI_OFFLINE=1 — the "
                    "credential-free path must use InMemoryEventStore.")
            from google.cloud import firestore
            self._db = firestore.Client(project=project_id or os.environ.get("GCP_PROJECT_ID", "hodi-2026"))

    def append(self, collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        try:
            self._db.collection(collection).document(doc_id).create(data)
        except gcloud_exceptions.AlreadyExists:
            raise DuplicateEventId(collection, doc_id)

    def read(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        coll = self._db.collection(collection)
        if filters:
            for k, v in filters.items():
                coll = coll.where(k, "==", v)
        return [doc.to_dict() for doc in coll.get()]


class DurableStoreUnavailable(RuntimeError):
    """The store could not be reached and this is not a declared offline run."""


def default_event_store():
    """
    InMemory under HODI_OFFLINE=1; Firestore otherwise — and a failure to
    build the Firestore client RAISES rather than degrading.

    This used to `except Exception: return InMemoryEventStore()`, which meant
    a credential problem in production silently turned the durable registry
    and Memory Bank into process-local dicts: agent publications would vanish
    on restart and cold-start re-hydration would return an empty fold, with
    nothing failing. That is the same shape as the gateway's fail-open, and
    it is the exact defect the durable store was built to remove. The offline
    twin is a declared mode, not a fallback.
    """
    if os.environ.get("HODI_OFFLINE") == "1":
        return InMemoryEventStore()
    try:
        return FirestoreEventStore()
    except Exception as e:
        raise DurableStoreUnavailable(
            f"No durable event store and HODI_OFFLINE is not set ({type(e).__name__}: {e}). "
            "Refusing to fall back to process memory — registry publications and memory-bank "
            "state would silently stop surviving restarts."
        ) from e
