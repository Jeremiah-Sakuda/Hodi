"""
Work-scoped authorization adversarial suite (HOD-701, HOD-702).

The property under test: the authorization tuple is
principal × work × requested scope × time — and every element is load-bearing.

Until 2026-08-14 there was no work dimension in the licensing path: the
gateway read was filtered by counterparty alone, so a buyer holding a
training grant for Work A was answered "permitted" — with a receipt — when
asking about Work B. A rights-management system answering that way is doing
RBAC, not administering resource-specific delegated rights.

Every test here goes through the REAL FastAPI route with a REAL signed
credential and the REAL gateway (offline documents injected through the
gateway's own offline path, so policy enforcement still runs). No
re-implementations: the 2026-08-13 build-log entry records exactly how a
test that asserts a local copy of the logic goes green while the route
stays wrong.
"""

import os
import json
import base64
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import buyer_api
from src.gateway.gateway import AgentGateway
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent
from src.api.auth import (
    InMemoryCredentialStore, compute_signature,
    HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE,
)

BUYER = "acme-intelligence-labs"
KEY, SECRET = "key-work-scope", "work-scope-secret-not-production"

WORK_A = "work-essay-001"
WORK_B = "work-audio-002"
FOREIGN_WORK = "work-of-another-artist-999"

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
GRANT_END = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _grant(grant_id, work_id, use_type, valid_until=None) -> dict:
    return GrantEvent(
        event_id=f"evt-{grant_id}",
        grant_id=grant_id,
        work_id=work_id,
        counterparty_id=BUYER,
        scope=Scope(use_type=use_type, model_class="all_models", commercial=True,
                    territory=["WW"], valid_from=T0, valid_until=valid_until),
        kind="granted",
        issued_at=T0,
        signature="s",
    ).model_dump(mode="json")


class TestWorkScopedAuthorization(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

        original_store = buyer_api._credential_store
        buyer_api.set_credential_store(InMemoryCredentialStore({
            KEY: {"counterparty_id": BUYER, "secret": SECRET, "active": True},
        }))
        self.addCleanup(lambda: buyer_api.set_credential_store(original_store))

        # The buyer's real position: a broad TRAINING grant on Work A, and a
        # narrow HUMAN_REFERENCE grant on Work B. Work-blind matching would
        # let the Work A grant answer for Work B.
        gateway = AgentGateway(offline_reads={"grants": [
            _grant("g-a-training", WORK_A, "training"),
            _grant("g-b-reference", WORK_B, "human_reference"),
            _grant("g-a-bounded", WORK_A, "synthesis", valid_until=GRANT_END),
        ]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))

        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)

    def _license(self, body: dict):
        raw = json.dumps(body).encode("utf-8")
        ts = datetime.now(timezone.utc).isoformat()
        return self.client.post("/api/v1/license", content=raw, headers={
            "Content-Type": "application/json",
            HEADER_KEY_ID: KEY, HEADER_TIMESTAMP: ts,
            HEADER_SIGNATURE: compute_signature(SECRET, KEY, ts, raw)})

    @staticmethod
    def _scope(use_type, valid_from="2026-08-06T00:00:00Z", valid_until=None):
        s = {"use_type": use_type, "model_class": "all_models", "commercial": False,
             "attribution_required": False, "territory": ["WW"], "valid_from": valid_from}
        if valid_until is not None:
            s["valid_until"] = valid_until
        return s

    def _body(self, work_id, scope):
        return {"work_id": work_id, "requested_scope": scope,
                "raw_document_b64": base64.b64encode(b"doc").decode()}

    # --- the five adversarial cases, verbatim from the review ---

    def test_training_grant_on_work_a_permits_work_a(self):
        r = self._license(self._body(WORK_A, self._scope("fine_tuning")))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["permitted"])
        self.assertEqual(r.json()["receipt"]["work_id"], WORK_A)
        self.assertEqual(r.json()["receipt"]["counterparty_id"], BUYER)

    def test_same_request_against_work_b_is_denied(self):
        """The defect this suite exists for: the SAME buyer, the SAME scope,
        a different work. The Work A training grant must not answer."""
        r = self._license(self._body(WORK_B, self._scope("fine_tuning")))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["permitted"],
                         "a grant for Work A licensed a request about Work B")
        self.assertIsNone(r.json()["receipt"])

    def test_work_b_grant_with_insufficient_scope_is_denied(self):
        """Work B carries only human_reference; training is above it in the
        lattice and must be refused ON WORK B'S OWN GRANT."""
        r = self._license(self._body(WORK_B, self._scope("training")))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["permitted"])

    def test_foreign_work_id_is_denied_without_leaking_existence(self):
        """A work_id this buyer holds nothing on: denied, and the response is
        byte-shaped exactly like any other refusal — it must not reveal
        whether the work exists, or whose it is."""
        r = self._license(self._body(FOREIGN_WORK, self._scope("human_reference")))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["permitted"])
        self.assertIsNone(body["receipt"])
        self.assertNotIn("artist", r.text)

    def test_missing_work_id_is_rejected_never_inferred(self):
        """No work_id: HTTP 422 at the schema. Inferring the resource from the
        grants the caller happens to hold is the same defect with a
        friendlier face."""
        body = {"requested_scope": self._scope("fine_tuning"),
                "raw_document_b64": base64.b64encode(b"doc").decode()}
        r = self._license(body)
        self.assertEqual(r.status_code, 422)

    # --- the two dimensions compose ---

    def test_bounded_grant_denies_request_window_extending_past_it(self):
        """HOD-702 through the real route: Work A's synthesis grant runs
        through Sep 1; a request through Dec 31 is refused even though the
        evaluation instant is inside the grant. (Asserted against synthesis,
        which only the bounded grant covers — training's unbounded grant does
        not contain synthesis, so nothing else can answer.)"""
        r = self._license(self._body(
            WORK_A, self._scope("synthesis", valid_until="2026-12-31T00:00:00Z")))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["permitted"])

    def test_bounded_grant_permits_request_window_inside_it(self):
        r = self._license(self._body(
            WORK_A, self._scope("synthesis", valid_until="2026-08-20T00:00:00Z")))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["permitted"])
        self.assertEqual(r.json()["receipt"]["grant_id"], "g-a-bounded")

    def test_malformed_request_interval_is_rejected_at_the_schema(self):
        r = self._license(self._body(
            WORK_A, self._scope("fine_tuning",
                                valid_from="2026-08-06T00:00:00Z",
                                valid_until="2026-08-05T00:00:00Z")))
        self.assertEqual(r.status_code, 422)

    def test_gateway_query_carries_both_filters(self):
        """The read itself must be constrained by counterparty AND work — the
        in-process post-filter is defense in depth, not the boundary. Spy on
        the gateway call to pin the query shape."""
        captured = {}
        gateway = AgentGateway(offline_reads={"grants": []})
        original = gateway.read_collection

        def spy(*args, **kwargs):
            captured.update(kwargs.get("filters") or {})
            return original(*args, **kwargs)

        gateway.read_collection = spy
        buyer_api.set_gateway(gateway)
        r = self._license(self._body(WORK_A, self._scope("fine_tuning")))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(captured.get("counterparty_id"), BUYER)
        self.assertEqual(captured.get("work_id"), WORK_A)


if __name__ == "__main__":
    unittest.main()
