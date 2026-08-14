"""
Storage fails closed (HOD-716).

The property under test: when durable storage is unreachable and the run has
NOT been declared offline, the system refuses — it never serves or accepts
process-local data as if it were the append-only log.

The defect this replaces: `_build_firestore_client` returned None on ANY
exception, and the gateway treats a missing client as the offline path. So a
credential problem in production turned every read into "no documents exist"
and every write into a buffer that dies with the instance — both answering
HTTP 200. An unfiltered "you hold no grants" is a licensing decision computed
against phantom state, and it looked exactly like a healthy one. The durable
event store had the same shape: a broken client silently became a dict, so
registry publications and memory-bank state would stop surviving restarts
with nothing failing.

`HODI_OFFLINE=1` remains a DECLARED mode — the credential-free demo and this
suite depend on it. The point is that it must be declared, not inferred from
a failure.
"""

import os
import unittest
from unittest.mock import patch

from src.gateway.gateway import AgentGateway, DurableStorageUnavailable, _build_firestore_client
from src.memory.event_store import (
    DurableStoreUnavailable, InMemoryEventStore, default_event_store)


class TestGatewayFailsClosed(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("HODI_OFFLINE")
        os.environ.pop("HODI_OFFLINE", None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop("HODI_OFFLINE", None)
        if self._saved is not None:
            os.environ["HODI_OFFLINE"] = self._saved

    def test_no_credentials_and_not_offline_raises(self):
        """The production failure: no ADC, no gcloud. Must raise, not degrade."""
        with patch("src.gateway.gateway.firestore.Client", side_effect=Exception("no ADC")), \
             patch("src.gateway.gateway.subprocess.check_output", side_effect=Exception("no gcloud")):
            with self.assertRaises(DurableStorageUnavailable):
                _build_firestore_client("hodi-2026")

    def test_constructing_a_gateway_without_storage_raises(self):
        """The failure surfaces at construction, before any handler can compute
        an answer from phantom state."""
        with patch("src.gateway.gateway.firestore.Client", side_effect=Exception("no ADC")), \
             patch("src.gateway.gateway.subprocess.check_output", side_effect=Exception("no gcloud")):
            with self.assertRaises(DurableStorageUnavailable):
                AgentGateway()

    def test_the_error_names_the_deliberate_offline_escape(self):
        """A fail-closed error that does not say how to run offline will be
        'fixed' by someone re-adding the fallback."""
        with patch("src.gateway.gateway.firestore.Client", side_effect=Exception("no ADC")), \
             patch("src.gateway.gateway.subprocess.check_output", side_effect=Exception("no gcloud")):
            with self.assertRaises(DurableStorageUnavailable) as ctx:
                _build_firestore_client("hodi-2026")
        self.assertIn("HODI_OFFLINE", str(ctx.exception))

    def test_declared_offline_still_returns_the_in_memory_path(self):
        """The credential-free demo must keep working — offline is a declared
        mode, and this is the paired positive."""
        os.environ["HODI_OFFLINE"] = "1"
        self.assertIsNone(_build_firestore_client("hodi-2026"))
        gateway = AgentGateway()
        self.assertIsNone(gateway.db)

    def test_gcloud_token_fallback_still_works_for_dev_shells(self):
        """The legitimate fallback (a dev shell with gcloud but no ADC) is
        preserved: failing closed must not break local development."""
        sentinel = object()
        with patch("src.gateway.gateway.firestore.Client",
                   side_effect=[Exception("no ADC"), sentinel]), \
             patch("src.gateway.gateway.subprocess.check_output", return_value=b"token"):
            self.assertIs(_build_firestore_client("hodi-2026"), sentinel)


class TestEventStoreFailsClosed(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("HODI_OFFLINE")
        os.environ.pop("HODI_OFFLINE", None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop("HODI_OFFLINE", None)
        if self._saved is not None:
            os.environ["HODI_OFFLINE"] = self._saved

    def test_default_store_raises_rather_than_becoming_a_dict(self):
        with patch("src.memory.event_store.FirestoreEventStore",
                   side_effect=Exception("no credentials")):
            with self.assertRaises(DurableStoreUnavailable):
                default_event_store()

    def test_declared_offline_returns_the_in_memory_twin(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.assertIsInstance(default_event_store(), InMemoryEventStore)

    def test_firestore_store_refuses_to_construct_under_declared_offline(self):
        """Belt and braces: the live store must not be reachable from a run
        that declared itself credential-free."""
        from src.memory.event_store import FirestoreEventStore
        os.environ["HODI_OFFLINE"] = "1"
        with self.assertRaises(RuntimeError):
            FirestoreEventStore()


if __name__ == "__main__":
    unittest.main()
