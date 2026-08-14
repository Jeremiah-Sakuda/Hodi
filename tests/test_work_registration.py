"""
Work registration (HOD-718).

The property under test: an artist can register a work through the running
system, and the manifest reflects it — without a code change or a deploy.

The gap this closes, named by an external review: `/works` returned a Python
literal, so "register your work with proof of control" was a claim the
deployed service could not honour. The corpus is now a labelled SEED that a
fold over real registrations extends.

The invariant that must survive the new write path: a registration cannot
reach `verified_control` without a stored proof (HOD-105). The route derives
the tier rather than accepting it, so the request body has no way to ask.
"""

import json
import unittest
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import buyer_api
from src.api.auth import (InMemoryCredentialStore, compute_signature,
                          HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE)
from src.gateway.gateway import AgentGateway
from tests.offline_env import force_offline

ARTIST, ARTIST_KEY, ARTIST_SECRET = "artist-jeremiah", "key-artist", "artist-secret-not-production"
BUYER_KEY, BUYER_SECRET = "key-buyer", "buyer-secret-not-production"
HASH = "a" * 64


def _body(**overrides):
    base = {
        "work_id": "work-new-001", "medium": "prose",
        "uri": "https://example.invalid/new-essay", "content_hash": HASH,
        "title": "A newly registered essay", "description": "registered through the API",
        "published_at": "2026-08-14T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestWorkRegistration(unittest.TestCase):
    def setUp(self):
        force_offline(self)
        self.gateway = AgentGateway()
        buyer_api.set_gateway(self.gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        original = buyer_api._credential_store
        buyer_api.set_credential_store(InMemoryCredentialStore({
            ARTIST_KEY: {"counterparty_id": ARTIST, "secret": ARTIST_SECRET,
                         "active": True, "principal_type": "artist"},
            BUYER_KEY: {"counterparty_id": "acme-intelligence-labs",
                        "secret": BUYER_SECRET, "active": True},
        }))
        self.addCleanup(lambda: buyer_api.set_credential_store(original))
        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)

    def _post(self, body, key=ARTIST_KEY, secret=ARTIST_SECRET):
        raw = json.dumps(body).encode()
        ts = datetime.now(timezone.utc).isoformat()
        return self.client.post("/api/v1/works", content=raw, headers={
            "Content-Type": "application/json", HEADER_KEY_ID: key,
            HEADER_TIMESTAMP: ts, HEADER_SIGNATURE: compute_signature(secret, key, ts, raw)})

    # --- the happy path ---

    def test_an_artist_can_register_a_work(self):
        r = self._post(_body())
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["work_id"], "work-new-001")
        self.assertEqual(body["artist_id"], ARTIST)
        # It is actually persisted, through the rights custodian.
        self.assertIn("work-new-001", self.gateway._offline_writes["works"])

    def test_the_registered_work_is_owned_by_the_CREDENTIAL_not_the_body(self):
        """artist_id is not a request field. A caller cannot register a work
        in someone else's name."""
        r = self._post(_body(artist_id="somebody-else"))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["artist_id"], ARTIST)

    # --- the control-tier invariant survives the new write path ---

    def test_registration_without_proof_is_asserted_not_verified(self):
        r = self._post(_body())
        self.assertEqual(r.json()["control_tier"], "asserted")
        self.assertIn("ASSERTED", r.json()["control_tier_reason"])

    def test_registration_with_a_proof_reaches_verified_control(self):
        r = self._post(_body(work_id="work-new-002", control_proof={
            "method": "well_known_file", "verified_at": "2026-08-14T00:00:00Z",
            "evidence_uri": "https://example.invalid/.well-known/hodi-proof.txt"}))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["control_tier"], "verified_control")

    def test_the_body_cannot_ask_for_verified_control(self):
        """The tier is DERIVED. Passing it is not a way in — the field is not
        part of the request schema, so it is ignored, and no proof still
        means asserted (HOD-105)."""
        r = self._post(_body(work_id="work-new-003", control_tier="verified_control"))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["control_tier"], "asserted")

    def test_a_malformed_proof_is_refused_not_downgraded(self):
        r = self._post(_body(work_id="work-new-004",
                             control_proof={"method": "telepathy", "verified_at": "x"}))
        self.assertEqual(r.status_code, 422)

    # --- authentication and collisions ---

    def test_an_unauthenticated_registration_is_refused(self):
        r = self.client.post("/api/v1/works", json=_body())
        self.assertEqual(r.status_code, 403)

    def test_a_buyer_credential_cannot_register_a_work(self):
        r = self._post(_body(work_id="work-new-005"), key=BUYER_KEY, secret=BUYER_SECRET)
        self.assertEqual(r.status_code, 403)
        self.assertIn("requires a 'artist' credential", r.json()["detail"])

    def test_a_taken_work_id_is_refused_uniformly(self):
        """A caller must not learn which ids are taken, or by whom."""
        self._post(_body(work_id="work-taken"))
        r = self._post(_body(work_id="work-taken", title="different work"))
        self.assertEqual(r.status_code, 403)
        self.assertIn("unavailable", r.json()["detail"])
        self.assertNotIn(ARTIST, r.json()["detail"])

    def test_a_malformed_work_id_is_rejected(self):
        self.assertEqual(self._post(_body(work_id="../../etc/passwd")).status_code, 422)
        self.assertEqual(self._post(_body(content_hash="not-a-hash")).status_code, 422)


class TestManifestReflectsRegistrations(unittest.TestCase):
    """The manifest is a fold over registrations plus the labelled seed."""

    def setUp(self):
        force_offline(self)

    def test_the_seed_corpus_is_labelled_as_such(self):
        from src.evidence_service import main
        works = main.get_registered_works()
        self.assertTrue(works, "the manifest served nothing at all")
        for w in works:
            self.assertIn(w["source"], ("seed_corpus", "registered"))

    def test_a_registered_work_appears_in_the_manifest(self):
        from src.evidence_service import main
        from src.schema.iam_policy import AGENT_SA_MAP

        gateway = AgentGateway()
        gateway.write_document(
            calling_sa=AGENT_SA_MAP["rights_custodian"]["sa_email"],
            calling_role_key="rights_custodian", target_collection="works",
            doc_id="work-live-001",
            data={"work_id": "work-live-001", "artist_id": ARTIST, "medium": "prose",
                  "uri": "https://example.invalid/x", "content_hash": HASH,
                  "control_tier": "asserted", "title": "Registered live",
                  "description": "", "published_at": "2026-08-14T00:00:00Z"})

        # The manifest builds its own gateway; point it at this one's data.
        import unittest.mock as mock
        with mock.patch.object(main, "AgentGateway", return_value=gateway, create=True):
            with mock.patch("src.gateway.gateway.AgentGateway", return_value=gateway):
                works = {w["work_id"]: w for w in main.get_registered_works()}
        self.assertIn("work-live-001", works)
        self.assertEqual(works["work-live-001"]["source"], "registered")
        # And the seed is still there — a registration extends, never replaces.
        self.assertIn("work-essay-001", works)

    def test_an_unreachable_registry_is_marked_never_implied_live(self):
        import unittest.mock as mock
        from src.evidence_service import main
        with mock.patch("src.gateway.gateway.AgentGateway",
                        side_effect=Exception("registry down")):
            works = main.get_registered_works()
        self.assertTrue(works, "the manifest should still serve the committed seed")
        for w in works:
            self.assertTrue(w.get("registry_unavailable"),
                            "a degraded manifest must say so, not look live")


if __name__ == "__main__":
    unittest.main()
