"""
Cross-buyer confidentiality attack suite (HOD-311, HOD-360).

These tests exist because the property was REFUTED on the live service on
2026-08-07: `POST /api/v1/license` took `counterparty_id` from the request body
and used it as both the query filter and the session context the gateway
checked that filter against, so an anonymous caller with the signature string
"NOT-A-REAL-SIGNATURE" read another counterparty's grant and was issued a
receipt in their name.

The property under test: a caller can obtain grant data for exactly the
counterparty their VERIFIED CREDENTIAL is bound to, and for no other — no
matter what the request body claims.

Every test runs offline against an in-memory credential store and an offline
gateway; none of them touch production Firestore.
"""

import os
import base64
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import buyer_api
from src.gateway.gateway import AgentGateway
from src.api.auth import (
    InMemoryCredentialStore, compute_signature, RequestAuthenticationError,
    HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE,
)
import json
from unittest.mock import patch
from src.schema.iam_policy import get_action_permission
from tests.offline_env import force_offline
from src.schema.iam_policy import AGENT_SA_MAP

VICTIM = "buyer-acme-2"
ATTACKER = "rival-labs"
VICTIM_KEY, VICTIM_SECRET = "key-victim", "victim-secret-do-not-use-in-prod"
ATTACKER_KEY, ATTACKER_SECRET = "key-attacker", "attacker-secret-do-not-use-in-prod"
ARTIST_KEY, ARTIST_SECRET = "key-artist", "artist-secret-do-not-use-in-prod"

SCOPE = {
    "use_type": "training", "model_class": "all_models", "commercial": True,
    "attribution_required": False, "territory": ["WW"],
    "valid_from": "2026-08-07T00:00:00Z",
}
# Every license body carries a work_id (HOD-701): the field is mandatory at
# the schema, so a body without it is refused as 422 BEFORE authentication —
# these tests each probe the auth layer, and must get past validation to do so.
WORK = "work-essay-001"
DOC_B64 = base64.b64encode(b"a buyer document").decode()


class TestCrossBuyerAuthentication(unittest.TestCase):
    def setUp(self):
        force_offline(self)

        store = InMemoryCredentialStore({
            VICTIM_KEY: {"counterparty_id": VICTIM, "secret": VICTIM_SECRET, "active": True},
            ATTACKER_KEY: {"counterparty_id": ATTACKER, "secret": ATTACKER_SECRET, "active": True},
            ARTIST_KEY: {"counterparty_id": "artist-jeremiah", "secret": ARTIST_SECRET,
                         "active": True, "principal_type": "artist"},
        })
        original = buyer_api._credential_store
        buyer_api.set_credential_store(store)
        self.addCleanup(lambda: buyer_api.set_credential_store(original))

        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)

    def _signed(self, key_id, secret, claimed=None, issued_at=None, scope=None,
                path="/api/v1/license", body=None):
        """Returns (path, raw_body_bytes, headers) for a correctly signed request."""
        issued_at = issued_at or datetime.now(timezone.utc).isoformat()
        if body is None:
            body = {"work_id": WORK, "requested_scope": scope or SCOPE, "raw_document_b64": DOC_B64}
        if claimed is not None:
            body = dict(body, counterparty_id=claimed)
        raw = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            HEADER_KEY_ID: key_id,
            HEADER_TIMESTAMP: issued_at,
            HEADER_SIGNATURE: compute_signature(secret, key_id, issued_at, raw),
        }
        return path, raw, headers

    def _post(self, path, raw, headers):
        return self.client.post(path, content=raw, headers=headers)

    # --- the exact live exploit, and its variants ---

    def test_unsigned_body_claiming_victim_is_rejected(self):
        """The verbatim live exploit: no credential, bogus signature, victim's id."""
        r = self.client.post("/api/v1/license", json={
            "counterparty_id": VICTIM, "work_id": WORK, "requested_scope": SCOPE,
            "raw_document_b64": DOC_B64,
        }, headers={HEADER_KEY_ID: "anything",
                    HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
                    HEADER_SIGNATURE: "NOT-A-REAL-SIGNATURE"})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("receipt_id", r.text)

    def test_request_with_no_signature_headers_at_all_is_rejected(self):
        r = self.client.post("/api/v1/license", json={
            "counterparty_id": VICTIM, "work_id": WORK, "requested_scope": SCOPE,
            "raw_document_b64": DOC_B64})
        self.assertEqual(r.status_code, 403)

    def test_attacker_credential_claiming_victim_is_rejected(self):
        """Authenticated as themselves, asking for the victim: refused, not downgraded."""
        r = self._post(*self._signed(ATTACKER_KEY, ATTACKER_SECRET, claimed=VICTIM))
        self.assertEqual(r.status_code, 403)
        self.assertIn("not bound to the claimed counterparty_id", r.json()["detail"])

    def test_victims_signature_replayed_with_swapped_key_id_is_rejected(self):
        path, raw, headers = self._signed(VICTIM_KEY, VICTIM_SECRET)
        headers[HEADER_KEY_ID] = ATTACKER_KEY
        r = self._post(path, raw, headers)
        self.assertEqual(r.status_code, 403)

    def test_tampering_with_signed_scope_after_signing_is_rejected(self):
        path, raw, headers = self._signed(ATTACKER_KEY, ATTACKER_SECRET)
        tampered = json.loads(raw)
        tampered["raw_document_b64"] = base64.b64encode(b"different document").decode()
        r = self._post(path, json.dumps(tampered).encode("utf-8"), headers)
        self.assertEqual(r.status_code, 403)

    def test_stale_signature_outside_freshness_window_is_rejected(self):
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        r = self._post(*self._signed(ATTACKER_KEY, ATTACKER_SECRET, issued_at=stale))
        self.assertEqual(r.status_code, 403)

    def test_unknown_key_and_bad_signature_are_indistinguishable(self):
        """Failure text must not let an attacker enumerate valid key_ids."""
        now = datetime.now(timezone.utc).isoformat()
        body = {"work_id": WORK, "requested_scope": SCOPE, "raw_document_b64": DOC_B64}
        unknown = self.client.post("/api/v1/license", json=body, headers={
            HEADER_KEY_ID: "key-does-not-exist", HEADER_TIMESTAMP: now, HEADER_SIGNATURE: "0" * 64})
        bad_sig = self.client.post("/api/v1/license", json=body, headers={
            HEADER_KEY_ID: ATTACKER_KEY, HEADER_TIMESTAMP: now, HEADER_SIGNATURE: "0" * 64})
        self.assertEqual(unknown.status_code, 403)
        self.assertEqual(bad_sig.status_code, 403)
        self.assertEqual(unknown.json()["detail"], bad_sig.json()["detail"])

    def test_revoked_credential_is_rejected(self):
        buyer_api.set_credential_store(InMemoryCredentialStore({
            ATTACKER_KEY: {"counterparty_id": ATTACKER, "secret": ATTACKER_SECRET, "active": False},
        }))
        r = self._post(*self._signed(ATTACKER_KEY, ATTACKER_SECRET))
        self.assertEqual(r.status_code, 403)

    def test_valid_credential_reaches_the_lattice_under_its_own_identity(self):
        """Positive pair: a correctly signed request authenticates and is
        evaluated. Offline the gateway returns no documents, so the lattice
        denies — the point is that it got past auth as ITSELF (HTTP 200)."""
        r = self._post(*self._signed(ATTACKER_KEY, ATTACKER_SECRET))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["permitted"])

    def test_identity_claim_denial_is_logged_as_a_structured_event(self):
        from src.gateway.gateway import AgentGateway
        gw = AgentGateway()
        denial = gw.log_identity_claim_denial(
            calling_sa=AGENT_SA_MAP["licensing_negotiator"]["sa_email"],
            authenticated_counterparty_id=ATTACKER, claimed_counterparty_id=VICTIM,
            key_id=ATTACKER_KEY)
        self.assertEqual(denial.outcome, "DENIED")
        self.assertEqual(denial.policy_consulted, "request_authentication_v1")
        self.assertIn(VICTIM, denial.reason)
        self.assertEqual(len(gw.denial_events), 1)

    # --- /api/v1/revoke: artist-side operation, artist credential required ---

    def test_revoke_is_not_reachable_unauthenticated(self):
        """This route shipped fully open: anyone could revoke any published
        work_id, the response disclosed every affected counterparty's terms,
        and append-only means the writes are not undoable."""
        r = self.client.post("/api/v1/revoke",
                             json={"work_id": "work-repo-001", "revoked_use_type": "training"})
        self.assertEqual(r.status_code, 403)

    def test_revoke_rejects_a_bogus_signature(self):
        r = self.client.post("/api/v1/revoke",
                             json={"work_id": "work-repo-001", "revoked_use_type": "training"},
                             headers={HEADER_KEY_ID: ARTIST_KEY,
                                      HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
                                      HEADER_SIGNATURE: "NOT-A-REAL-SIGNATURE"})
        self.assertEqual(r.status_code, 403)

    def test_counterparty_credential_cannot_revoke(self):
        """A buyer must not be able to terminate an artist's grants — including
        a rival's. Valid credential, wrong principal type."""
        r = self._post(*self._signed(
            ATTACKER_KEY, ATTACKER_SECRET, path="/api/v1/revoke",
            body={"work_id": "work-repo-001", "revoked_use_type": "training"}))
        self.assertEqual(r.status_code, 403)
        self.assertIn("requires a 'artist' credential", r.json()["detail"])

    def test_artist_credential_is_accepted_by_revoke_when_it_owns_the_work(self):
        """Positive: the artist credential authenticates AND owns the work.
        Offline the injected gateway holds the `works` row; the cascade affects
        nothing (no grants offline), the point is that auth + ownership passed."""
        gateway = AgentGateway(offline_reads={
            "works": [{"work_id": "work-repo-001", "artist_id": "artist-jeremiah"}]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        r = self._post(*self._signed(
            ARTIST_KEY, ARTIST_SECRET, path="/api/v1/revoke",
            body={"work_id": "work-repo-001", "revoked_use_type": "training"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["affected_grants"], [])

    def test_live_revoke_delegates_to_private_worker(self):
        """With a deployed worker configured, the front door must not execute
        the propagator locally under its own workload identity."""
        from src.agents.revocation_propagator import CascadeResult

        gateway = AgentGateway(offline_reads={
            "works": [{"work_id": "work-repo-001", "artist_id": "artist-jeremiah"}]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        result = CascadeResult(
            operation_id="operation-remote-1", revoked_use_type="training",
            derived_scopes=[], structured_derivation=[], affected_grants=[],
            issued_notices=[], replayed_effects=0)

        with patch.dict(os.environ, {
                "HODI_OFFLINE": "0",
                "HODI_REVOCATION_WORKER_URL": "https://worker.example"}), \
             patch.object(buyer_api, "execute_remote_revocation", return_value=result) as remote, \
             patch.object(buyer_api.RevocationPropagatorAgent,
                          "execute_revocation_cascade",
                          side_effect=AssertionError("front door executed the cascade locally")):
            r = self._post(*self._signed(
                ARTIST_KEY, ARTIST_SECRET, path="/api/v1/revoke",
                body={"work_id": "work-repo-001", "revoked_use_type": "training",
                      "operation_id": "operation-remote-1"}))

        self.assertEqual(r.status_code, 200)
        remote.assert_called_once_with(
            "https://worker.example", work_id="work-repo-001",
            revoked_use_type="training", operation_id="operation-remote-1")

    def test_private_worker_failure_fails_closed_without_local_fallback(self):
        from src.gateway.revocation_client import RevocationWorkerUnavailable

        gateway = AgentGateway(offline_reads={
            "works": [{"work_id": "work-repo-001", "artist_id": "artist-jeremiah"}]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))

        with patch.dict(os.environ, {
                "HODI_OFFLINE": "0",
                "HODI_REVOCATION_WORKER_URL": "https://worker.example"}), \
             patch.object(buyer_api, "execute_remote_revocation",
                          side_effect=RevocationWorkerUnavailable("timed out")), \
             patch.object(buyer_api.RevocationPropagatorAgent,
                          "execute_revocation_cascade",
                          side_effect=AssertionError("fail-open local fallback")):
            r = self._post(*self._signed(
                ARTIST_KEY, ARTIST_SECRET, path="/api/v1/revoke",
                body={"work_id": "work-repo-001", "revoked_use_type": "training"}))

        self.assertEqual(r.status_code, 503)
        self.assertIn("no effects were initiated", r.json()["detail"])

    def test_artist_cannot_revoke_a_work_they_do_not_own(self):
        """The finding: an artist credential must not revoke ANY work — only its
        own. A work owned by a different artist is refused, before any append."""
        gateway = AgentGateway(offline_reads={
            "works": [{"work_id": "work-repo-001", "artist_id": "someone-else"}]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        r = self._post(*self._signed(
            ARTIST_KEY, ARTIST_SECRET, path="/api/v1/revoke",
            body={"work_id": "work-repo-001", "revoked_use_type": "training"}))
        self.assertEqual(r.status_code, 403)
        self.assertIn("does not own", r.json()["detail"])

    def test_revoking_an_unknown_work_is_refused(self):
        """A missing work is a uniform 403 — an artist must not enumerate work
        ids or owners by probing revoke."""
        gateway = AgentGateway(offline_reads={"works": []})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        r = self._post(*self._signed(
            ARTIST_KEY, ARTIST_SECRET, path="/api/v1/revoke",
            body={"work_id": "work-does-not-exist", "revoked_use_type": "training"}))
        self.assertEqual(r.status_code, 403)

    def test_artist_credential_cannot_negotiate_as_a_buyer(self):
        """The principal-type check runs both ways."""
        r = self._post(*self._signed(ARTIST_KEY, ARTIST_SECRET))
        self.assertEqual(r.status_code, 403)
        self.assertIn("requires a 'counterparty' credential", r.json()["detail"])

    def test_principal_type_denial_is_logged_as_a_structured_event(self):
        from src.gateway.gateway import AgentGateway
        gw = AgentGateway()
        denial = gw.log_principal_type_denial(
            calling_sa="revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
            key_id=ATTACKER_KEY, principal_type="counterparty",
            required_principal_type="artist", operation="/api/v1/revoke")
        self.assertEqual(denial.outcome, "DENIED")
        self.assertEqual(denial.policy_consulted, "principal_type_policy_v1")
        self.assertEqual(len(gw.denial_events), 1)

    def test_natural_language_endpoint_enforces_the_same_boundary(self):
        r = self._post(*self._signed(
            ATTACKER_KEY, ATTACKER_SECRET, claimed=VICTIM, path="/api/v1/license/natural",
            body={"work_id": WORK, "request_text": "we would like to fine-tune on this work"}))
        self.assertEqual(r.status_code, 403)


class TestIamPolicyMatching(unittest.TestCase):
    """The second, independent hole: prefix matching turned a path template into
    a collection-wide grant, and denied_collections was never consulted."""

    def test_buyer_terms_requires_the_session_filter_key(self):
        permitted, required = get_action_permission("licensing_negotiator", "buyer_terms")
        self.assertTrue(permitted)
        self.assertEqual(required, "counterparty_id")

    def test_prefix_matching_does_not_grant_unrelated_collections(self):
        for collection in ("buyer_terms_archive", "grants_backup", "receipts_export"):
            permitted, _ = get_action_permission("licensing_negotiator", collection)
            self.assertFalse(permitted, f"'{collection}' must not be permitted by prefix match")

    def test_denied_collections_are_consulted_and_absolute(self):
        for role, collection in (("licensing_negotiator", "artists"),
                                 ("evidence_agent", "buyer_terms"),
                                 ("revocation_propagator", "artists"),
                                 ("rights_custodian", "buyer_terms")):
            permitted, _ = get_action_permission(role, collection)
            self.assertFalse(permitted, f"{role} must be denied '{collection}'")

    def test_a_denial_OVERRIDES_a_permission_for_the_same_collection(self):
        """The deny-check was INERT: no collection appeared in both lists, so
        deleting the check entirely produced byte-identical output and the test
        above still passed. `denied_collections` only means something if a deny
        can beat a grant — assert that directly."""
        import src.schema.iam_policy as policy
        role = "licensing_negotiator"
        original = policy.AGENT_SA_MAP[role]["denied_collections"]
        try:
            permitted, _ = get_action_permission(role, "receipts")
            self.assertTrue(permitted, "precondition: 'receipts' is normally permitted")
            policy.AGENT_SA_MAP[role]["denied_collections"] = list(original) + ["receipts"]
            permitted, _ = get_action_permission(role, "receipts")
            self.assertFalse(
                permitted,
                "a collection in BOTH lists must be DENIED — denials are absolute, "
                "and if they are not, denied_collections is decoration")
        finally:
            policy.AGENT_SA_MAP[role]["denied_collections"] = original

    def test_a_denial_beats_a_permission_carrying_a_required_filter(self):
        """Same property on the filtered-collection path, which returns early."""
        import src.schema.iam_policy as policy
        role = "licensing_negotiator"
        original = policy.AGENT_SA_MAP[role]["denied_collections"]
        try:
            policy.AGENT_SA_MAP[role]["denied_collections"] = list(original) + ["grants"]
            permitted, required = get_action_permission(role, "grants")
            self.assertFalse(permitted)
            self.assertIsNone(required)
        finally:
            policy.AGENT_SA_MAP[role]["denied_collections"] = original

    def test_negotiator_agent_denied_other_counterparty_by_policy_not_by_local_check(self):
        from src.agents.licensing_negotiator import LicensingNegotiatorAgent
        agent = LicensingNegotiatorAgent(session_counterparty_id="buyer-session-1")
        self.assertEqual(agent.get_session_buyer_terms()["status"], "SUCCESS")
        with self.assertRaises(PermissionError):
            agent.get_other_buyer_terms("buyer-session-rival-corp")
        with self.assertRaises(PermissionError):
            agent.get_unfiltered_buyer_terms()


class NoSignatureValueIsSpecialTest(unittest.TestCase):
    """A magic signature value must never authenticate (HOD-750).

    535 tests asserted that a WRONG signature is refused, and not one asserted
    that no PARTICULAR value is privileged. So an added clause of the form

        if signature != "MASTERKEY" and not hmac.compare_digest(expected, signature):

    passed every CI target — a backdoor whose diff is nine characters, in the
    one function standing between an anonymous request and every counterparty's
    grants. "Rejects a bad signature" and "has no accepted constant" are
    different properties; the suite only had the first.

    The sweep below is deliberately broad and cheap: real credentials are the
    only thing that authenticates, so every value that is not the computed HMAC
    must fail, including the ones a backdoor would plausibly choose.
    """

    KEY_ID = "key-backdoor-probe"
    SECRET = "a-real-registered-secret"

    def setUp(self):
        self.store = InMemoryCredentialStore({
            self.KEY_ID: {"secret": self.SECRET, "counterparty_id": "buyer-probe",
                          "principal_type": "buyer", "active": True},
        })
        self.body = b'{"probe":true}'
        self.issued_at = datetime.now(timezone.utc).isoformat()

    def _authenticate(self, signature):
        from src.api.auth import authenticate
        return authenticate(key_id=self.KEY_ID, issued_at=self.issued_at,
                            signature=signature, body=self.body, store=self.store)

    def test_the_real_signature_still_authenticates(self):
        """Guard the guard: if this fails, every case below passes vacuously."""
        good = compute_signature(self.SECRET, self.KEY_ID, self.issued_at, self.body)
        self.assertEqual(self._authenticate(good).counterparty_id, "buyer-probe")

    def test_no_magic_value_authenticates(self):
        candidates = [
            "MASTERKEY", "masterkey", "DEBUG", "debug", "TEST", "test",
            "BYPASS", "bypass", "ADMIN", "admin", "root", "*", "true", "1",
            "0" * 64, "f" * 64, "-", "null", "None", "undefined",
            compute_signature("the-wrong-secret", self.KEY_ID, self.issued_at, self.body),
        ]
        for value in candidates:
            with self.subTest(signature=value):
                with self.assertRaises(RequestAuthenticationError):
                    self._authenticate(value)

    def test_a_signature_valid_for_a_different_body_is_refused(self):
        """The other shape of the same mistake: comparing against something the
        caller can influence."""
        other = compute_signature(self.SECRET, self.KEY_ID, self.issued_at, b'{"probe":false}')
        with self.assertRaises(RequestAuthenticationError):
            self._authenticate(other)


if __name__ == "__main__":
    unittest.main()
