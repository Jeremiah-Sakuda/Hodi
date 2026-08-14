"""
The GATEWAY copy of the cross-buyer rule, and the handler's fold (HOD-107, HOD-311, HOD-312).

Two mutations survived the full 203-test suite because of what was NOT tested:

  M12  Neutering the session-context comparison in `gateway.py::_enforce` left
       every test green. `grep -rn session_context tests/` returned ZERO hits.
       The rule is implemented twice — `gateway.py::_enforce` (what the deployed
       API and the public debug endpoint call) and `agents/base.py::access_collection`
       (what the existing IAM tests instantiate) — and only the second copy was
       covered. A CI running the suite alone would have shipped the exact
       regression BUILD-LOG correction #5 is about.

  M18  Replacing `active_grant_events(all_events)` with a raw `granted` filter in
       the `/api/v1/license` handler left the suite green AND `make demo` at
       exit 0. Truth-table case 46 asserts the property on `permits()`; nothing
       asserted that the HANDLER folds before asking.

Both are offline. Neither needed credentials. They just did not exist.
"""

import base64
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import buyer_api
from src.api.auth import (
    InMemoryCredentialStore, compute_signature,
    HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE,
)
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope

NEGOTIATOR_SA = "licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com"
SESSION = "acme-intelligence-labs"
RIVAL = "buyer-acme-2"


class TestGatewaySessionScopeEnforcement(unittest.TestCase):
    """Directly against `gateway.py::_enforce` — the copy the deployed API uses."""

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.gateway = AgentGateway()

    def read(self, filters, session_context):
        return self.gateway.read_collection(
            calling_sa=NEGOTIATOR_SA, calling_role_key="licensing_negotiator",
            target_collection="grants", filters=filters, session_context=session_context)

    def test_filter_matching_the_session_is_permitted(self):
        """Paired positive — without it, a gateway that denies everything passes."""
        self.assertEqual(self.read({"counterparty_id": SESSION}, {"counterparty_id": SESSION}), [])
        self.assertEqual(self.gateway.denial_events, [])

    def test_filter_naming_another_counterparty_is_denied(self):
        """THE cross-buyer rule, on the gateway copy. This had no test."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.read({"counterparty_id": RIVAL}, {"counterparty_id": SESSION})
        self.assertIn("outside of session context", str(ctx.exception))
        self.assertEqual(self.gateway.denial_events[-1].attempted_filters,
                         {"counterparty_id": RIVAL})
        self.assertEqual(self.gateway.denial_events[-1].session_context,
                         {"counterparty_id": SESSION})

    def test_absent_session_context_is_denied_not_skipped(self):
        """Fail closed. The check used to run only when the caller supplied
        context, so omitting it was the permissive path."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.read({"counterparty_id": RIVAL}, None)
        self.assertIn("supplied no session context", str(ctx.exception))

    def test_absent_session_context_is_denied_even_when_the_filter_looks_right(self):
        """The dangerous variant: a caller that omits context but filters
        'correctly' must still be denied, or omitting context is a bypass."""
        with self.assertRaises(GatewayPolicyDenial):
            self.read({"counterparty_id": SESSION}, None)

    def test_missing_filter_is_denied(self):
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.read(None, {"counterparty_id": SESSION})
        self.assertIn("MUST scope query", str(ctx.exception))

    def test_every_denial_is_recorded_as_a_structured_event(self):
        for filters, ctx_ in (({"counterparty_id": RIVAL}, {"counterparty_id": SESSION}),
                              (None, {"counterparty_id": SESSION}),
                              ({"counterparty_id": SESSION}, None)):
            with self.assertRaises(GatewayPolicyDenial):
                self.read(filters, ctx_)
        self.assertEqual(len(self.gateway.denial_events), 3)
        for denial in self.gateway.denial_events:
            self.assertEqual(denial.outcome, "DENIED")
            self.assertEqual(denial.policy_consulted, "gateway_policy_v1")

    def test_the_two_implementations_of_the_rule_agree(self):
        """The rule lives in gateway.py AND agents/base.py. Only one was tested,
        which is how one copy could rot silently. Assert they answer alike."""
        from src.agents.base import BaseAgent
        agent = BaseAgent("licensing_negotiator")
        cases = [
            ({"counterparty_id": SESSION}, {"counterparty_id": SESSION}, True),
            ({"counterparty_id": RIVAL}, {"counterparty_id": SESSION}, False),
            (None, {"counterparty_id": SESSION}, False),
            ({"counterparty_id": SESSION}, None, False),
        ]
        for filters, ctx_, expect_ok in cases:
            with self.subTest(filters=filters, session=ctx_):
                try:
                    self.gateway.read_collection(
                        calling_sa=NEGOTIATOR_SA, calling_role_key="licensing_negotiator",
                        target_collection="grants", filters=filters, session_context=ctx_)
                    gateway_ok = True
                except GatewayPolicyDenial:
                    gateway_ok = False
                try:
                    agent.access_collection("grants", filters=filters, session_context=ctx_)
                    agent_ok = True
                except PermissionError:
                    agent_ok = False
                self.assertEqual(gateway_ok, expect_ok)
                self.assertEqual(agent_ok, expect_ok,
                                 "the two implementations of the cross-buyer rule disagree")


class TestLicenseHandlerFoldsBeforeContainment(unittest.TestCase):
    """
    The handler must fold the append-only log before asking `permits()`.

    The gateway returns raw events, including a revoked grant's original
    `granted` event. If the handler passes those straight through, a revoked
    grant still licenses — the defect class BUILD-LOG already documents, in the
    production request path.
    """

    KEY, SECRET = "key-fold-test", "fold-test-secret-not-production"

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

        original = buyer_api._credential_store
        buyer_api.set_credential_store(InMemoryCredentialStore({
            self.KEY: {"counterparty_id": SESSION, "secret": self.SECRET, "active": True},
        }))
        self.addCleanup(lambda: buyer_api.set_credential_store(original))

        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)

        t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
        broad = Scope(use_type="training", model_class="all_models", commercial=True,
                      territory=["WW"], valid_from=t0)
        # An append-only log for ONE grant: granted, then revoked. Nothing is active.
        self.raw_events = [
            GrantEvent(event_id="e1", grant_id="g-fold", work_id="w", counterparty_id=SESSION,
                       scope=broad, kind="granted", issued_at=t0, signature="s").model_dump(mode="json"),
            GrantEvent(event_id="e2", grant_id="g-fold", work_id="w", counterparty_id=SESSION,
                       scope=broad, kind="revoked", issued_at=t0 + timedelta(days=1),
                       signature="s").model_dump(mode="json"),
        ]

    def _post(self, path, body):
        raw = json.dumps(body).encode("utf-8")
        ts = datetime.now(timezone.utc).isoformat()
        return self.client.post(path, content=raw, headers={
            "Content-Type": "application/json",
            HEADER_KEY_ID: self.KEY, HEADER_TIMESTAMP: ts,
            HEADER_SIGNATURE: compute_signature(self.SECRET, self.KEY, ts, raw)})

    @staticmethod
    def _reads(grant_events):
        """Patched read_collection: serves the grant fixture for `grants` and
        an empty set for everything else — the handler now also reads
        `negotiation_freezes` (HOD-705 containment gate), and a patch that
        answered EVERY collection with grant events would freeze the caller."""
        def _side_effect(*args, **kwargs):
            target = kwargs.get("target_collection") or (args[2] if len(args) > 2 else None)
            return grant_events if target == "grants" else []
        return _side_effect

    def test_a_revoked_grant_does_not_license_through_the_handler(self):
        with patch.object(AgentGateway, "read_collection",
                          side_effect=self._reads(self.raw_events)):
            r = self._post("/api/v1/license", {
                "work_id": "w",
                "requested_scope": {
                    "use_type": "training", "model_class": "all_models", "commercial": True,
                    "attribution_required": False, "territory": ["WW"],
                    "valid_from": "2026-08-06T00:00:00Z"},
                "raw_document_b64": base64.b64encode(b"doc").decode()})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["permitted"],
                         "the handler licensed against a REVOKED grant — it is not folding")
        self.assertIsNone(r.json()["receipt"])

    def test_an_active_grant_still_licenses(self):
        """Paired positive: folding must not deny everything."""
        active_only = [self.raw_events[0]]
        with patch.object(AgentGateway, "read_collection",
                          side_effect=self._reads(active_only)):
            r = self._post("/api/v1/license", {
                "work_id": "w",
                "requested_scope": {
                    "use_type": "fine_tuning", "model_class": "open_weights", "commercial": False,
                    "attribution_required": False, "territory": ["US"],
                    "valid_from": "2026-08-06T00:00:00Z"},
                "raw_document_b64": base64.b64encode(b"doc").decode()})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["permitted"])
        self.assertEqual(r.json()["receipt"]["counterparty_id"], SESSION)


if __name__ == "__main__":
    unittest.main()
