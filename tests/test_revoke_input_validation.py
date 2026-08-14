"""
tests/test_revoke_input_validation.py — `revoked_use_type` is vocabulary, not
free text (HOD-104, HOD-107).

`RevokeRequest.revoked_use_type` shipped as a bare `str`. "Training" (wrong
case), "podcasting" (not a use type) and "" all authenticated, ran the cascade,
matched nothing, and returned **HTTP 200 with an empty result** — a revocation
that reported success and terminated nothing.

The mechanism: `USE_TYPE_CONTAINMENT.get(x, {x})` degrades an unknown key to a
single-element set, which matches no grant. So the failure was silent by
construction rather than by oversight, and an artist revoking with a typo would
have been told it worked.

This is the same shape as the two live auth defects — a check whose enforcement
depended on the caller supplying something sensible — and the answer is the same:
refuse at the boundary. The field is now the `UseType` literal, so FastAPI
rejects it with 422 and the valid vocabulary before any handler code runs.

Offline; no credential store or Firestore access is reached, because validation
happens first.
"""

import base64
import json
import os
import unittest
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import buyer_api
from src.api.auth import (
    InMemoryCredentialStore, compute_signature,
    HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE,
)
from src.schema.scope import UseType
from typing import get_args
from tests.offline_env import force_offline

ARTIST_KEY, ARTIST_SECRET = "key-artist", "artist-secret-do-not-use-in-prod"

VALID_USE_TYPES = set(get_args(UseType))
REJECTED = ["Training", "TRAINING", "podcasting", "", "training ", "fine-tuning",
            "*", "training,fine_tuning"]


class RevokeUseTypeValidationTest(unittest.TestCase):
    def setUp(self):
        force_offline(self)

        store = InMemoryCredentialStore({
            ARTIST_KEY: {"counterparty_id": "artist-jeremiah", "secret": ARTIST_SECRET,
                         "active": True, "principal_type": "artist"},
        })
        original = buyer_api._credential_store
        buyer_api.set_credential_store(store)
        self.addCleanup(lambda: buyer_api.set_credential_store(original))

        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)

    def _signed_revoke(self, revoked_use_type, work_id="work-does-not-exist-probe"):
        """Signed by a real artist credential, so a 422 can only come from the
        schema — never from authentication. Probes a work_id that matches
        nothing, so a regression here still writes no events."""
        body = {"work_id": work_id, "revoked_use_type": revoked_use_type}
        raw = json.dumps(body).encode("utf-8")
        issued_at = datetime.now(timezone.utc).isoformat()
        return self.client.post("/api/v1/revoke", content=raw, headers={
            "Content-Type": "application/json",
            HEADER_KEY_ID: ARTIST_KEY,
            HEADER_TIMESTAMP: issued_at,
            HEADER_SIGNATURE: compute_signature(ARTIST_SECRET, ARTIST_KEY, issued_at, raw),
        })

    def test_the_vocabulary_is_the_lattice_vocabulary(self):
        """Guards against the literal and the lattice drifting apart — if a use
        type is added to one and not the other, this fails rather than silently
        making the new type unrevocable."""
        from src.schema.lattice import USE_TYPE_CONTAINMENT
        self.assertEqual(VALID_USE_TYPES, set(USE_TYPE_CONTAINMENT),
                         "UseType and USE_TYPE_CONTAINMENT disagree about the vocabulary")

    def test_bogus_use_types_are_refused_with_422(self):
        for bad in REJECTED:
            with self.subTest(revoked_use_type=bad):
                r = self._signed_revoke(bad)
                self.assertEqual(r.status_code, 422,
                                 f"{bad!r} was accepted — a silent no-op revocation")

    def test_a_refusal_never_reports_a_cascade(self):
        """The damaging part was not the status code, it was the body: a
        CascadeResult shaped like success."""
        for bad in REJECTED:
            with self.subTest(revoked_use_type=bad):
                text = self._signed_revoke(bad).text
                self.assertNotIn("affected_grants", text)
                self.assertNotIn("issued_notices", text)

    def test_the_error_names_the_valid_vocabulary(self):
        """An artist who typos should be told what to type."""
        detail = self._signed_revoke("Training").text
        for use_type in VALID_USE_TYPES:
            self.assertIn(use_type, detail,
                          f"422 body does not name the valid use type {use_type!r}")

    def test_every_valid_use_type_still_passes_validation(self):
        """The guard must not be so tight it refuses the real vocabulary. A
        matching-nothing work_id means these are structurally write-free."""
        for good in sorted(VALID_USE_TYPES):
            with self.subTest(revoked_use_type=good):
                self.assertNotEqual(self._signed_revoke(good).status_code, 422,
                                    f"{good!r} is a real use type and must validate")

    def test_missing_use_type_is_refused(self):
        raw = json.dumps({"work_id": "work-does-not-exist-probe"}).encode("utf-8")
        issued_at = datetime.now(timezone.utc).isoformat()
        r = self.client.post("/api/v1/revoke", content=raw, headers={
            "Content-Type": "application/json",
            HEADER_KEY_ID: ARTIST_KEY,
            HEADER_TIMESTAMP: issued_at,
            HEADER_SIGNATURE: compute_signature(ARTIST_SECRET, ARTIST_KEY, issued_at, raw),
        })
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
