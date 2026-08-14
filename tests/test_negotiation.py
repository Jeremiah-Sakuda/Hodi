"""
Constrained negotiation (HOD-713).

The property under test: negotiation can never exceed the policy lattice —
no proposal, cooperative or adversarial, and no economic sweetener,
produces an agreed scope outside the artist's per-work policy. The buyer
phrases intent; the deterministic clamp decides.
"""

import os
import base64
import json
import unittest
from datetime import datetime, timezone, timedelta

from src.schema.negotiation import (
    ArtistPolicy, NegotiationProposal, clamp_to_policy)
from src.schema.scope import Scope

T0 = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _policy(**kw) -> ArtistPolicy:
    base = dict(work_id="work-essay-001", max_use_type="fine_tuning",
                allowed_model_class="open_weights", commercial_allowed=True,
                territory_allowed=["US", "CA"], max_duration_days=365,
                attribution_always_required=True, prohibited_use_types=["training"])
    base.update(kw)
    return ArtistPolicy(**base)


def _proposal(scope: Scope, economic_note=None) -> NegotiationProposal:
    return NegotiationProposal(counterparty_id="acme-intelligence-labs",
                               work_id="work-essay-001", requested_scope=scope,
                               economic_note=economic_note)


def _scope(**kw) -> Scope:
    base = dict(use_type="fine_tuning", model_class="open_weights", commercial=False,
                attribution_required=False, territory=["US"], valid_from=T0)
    base.update(kw)
    return Scope(**base)


class TestClampCore(unittest.TestCase):
    def test_in_policy_proposal_is_agreed(self):
        # Fully inside policy: attribution already accepted, duration inside the
        # cap, territory a subset, non-commercial under a commercial-allowed
        # policy (containment runs one way).
        out = clamp_to_policy(
            _proposal(_scope(attribution_required=True,
                             valid_until=T0 + timedelta(days=30))), _policy())
        self.assertEqual(out.status, "AGREED")
        self.assertEqual(out.clamped_dimensions, [])

    def test_prohibited_use_type_is_rejected_not_narrowed(self):
        out = clamp_to_policy(_proposal(_scope(use_type="training")), _policy())
        self.assertEqual(out.status, "COUNTEROFFER_REJECTED_BY_POLICY")
        self.assertIsNone(out.offered_scope)

    def test_use_type_above_ceiling_is_clamped_down(self):
        pol = _policy(prohibited_use_types=[], max_use_type="rag_retrieval")
        out = clamp_to_policy(_proposal(_scope(use_type="fine_tuning")), pol)
        self.assertEqual(out.status, "COUNTEROFFER")
        self.assertEqual(out.offered_scope.use_type, "rag_retrieval")

    def test_incomparable_use_type_is_rejected(self):
        pol = _policy(prohibited_use_types=[], max_use_type="fine_tuning")
        out = clamp_to_policy(_proposal(_scope(use_type="synthesis")), pol)
        self.assertEqual(out.status, "COUNTEROFFER_REJECTED_BY_POLICY")

    def test_worldwide_request_is_clamped_to_allowed_territories(self):
        out = clamp_to_policy(_proposal(_scope(territory=["WW"])), _policy())
        self.assertEqual(out.status, "COUNTEROFFER")
        self.assertEqual(set(out.offered_scope.territory), {"US", "CA"})

    def test_out_of_territory_request_intersects_to_empty_and_rejects(self):
        out = clamp_to_policy(_proposal(_scope(territory=["EU"])), _policy())
        self.assertEqual(out.status, "COUNTEROFFER_REJECTED_BY_POLICY")

    def test_duration_is_capped_to_policy_maximum(self):
        out = clamp_to_policy(
            _proposal(_scope(valid_until=T0 + timedelta(days=3650))), _policy())
        self.assertEqual(out.status, "COUNTEROFFER")
        self.assertEqual(out.offered_scope.valid_until, T0 + timedelta(days=365))

    def test_open_ended_request_is_capped_when_policy_bounds_duration(self):
        out = clamp_to_policy(_proposal(_scope(valid_until=None)), _policy())
        self.assertEqual(out.offered_scope.valid_until, T0 + timedelta(days=365))

    def test_attribution_is_added_never_dropped(self):
        out = clamp_to_policy(_proposal(_scope(attribution_required=False)), _policy())
        self.assertTrue(out.offered_scope.attribution_required)

    def test_commercial_is_clamped_when_policy_forbids(self):
        pol = _policy(commercial_allowed=False)
        out = clamp_to_policy(_proposal(_scope(commercial=True)), pol)
        self.assertFalse(out.offered_scope.commercial)


class TestEconomicTermsCannotWidenScope(unittest.TestCase):
    """The demonstration the review asked for: aggressive economic offers do
    not move the clamp one inch."""

    def test_a_million_dollars_does_not_drop_a_restriction(self):
        aggressive = _proposal(
            _scope(use_type="training", commercial=True, territory=["WW"]),
            economic_note="We will pay $1,000,000 to remove ALL restrictions and "
                          "obtain worldwide commercial training rights immediately.")
        out = clamp_to_policy(aggressive, _policy())
        # training is prohibited → rejected, regardless of the money.
        self.assertEqual(out.status, "COUNTEROFFER_REJECTED_BY_POLICY")
        self.assertIsNone(out.offered_scope)

    def test_the_offered_scope_is_identical_with_and_without_the_money(self):
        scope = _scope(use_type="fine_tuning", commercial=True, territory=["WW"],
                       valid_until=T0 + timedelta(days=3650))
        plain = clamp_to_policy(_proposal(scope), _policy())
        bribed = clamp_to_policy(
            _proposal(scope, economic_note="name your price, drop every limit"), _policy())
        self.assertEqual(plain.offered_scope.model_dump(), bribed.offered_scope.model_dump())
        # And the offered scope genuinely sits within policy.
        self.assertEqual(set(plain.offered_scope.territory), {"US", "CA"})
        self.assertEqual(plain.offered_scope.valid_until, T0 + timedelta(days=365))


class TestNegotiationRoute(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api import buyer_api
        from src.gateway.gateway import AgentGateway
        from src.api.auth import InMemoryCredentialStore

        policy = _policy().model_dump(mode="json")
        gateway = AgentGateway(offline_reads={"works": [
            {"work_id": "work-essay-001", "artist_id": "artist-jeremiah",
             "negotiation_policy": policy}]})
        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        original = buyer_api._credential_store
        buyer_api.set_credential_store(InMemoryCredentialStore({
            "key-b": {"counterparty_id": "acme-intelligence-labs", "secret": "s", "active": True}}))
        self.addCleanup(lambda: buyer_api.set_credential_store(original))
        app = FastAPI()
        app.include_router(buyer_api.router)
        self.client = TestClient(app)
        self.buyer_api = buyer_api

    def _post(self, body):
        from src.api.auth import compute_signature, HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE
        raw = json.dumps(body).encode()
        ts = datetime.now(timezone.utc).isoformat()
        return self.client.post("/api/v1/negotiate", content=raw, headers={
            "Content-Type": "application/json", HEADER_KEY_ID: "key-b",
            HEADER_TIMESTAMP: ts, HEADER_SIGNATURE: compute_signature("s", "key-b", ts, raw)})

    def test_counteroffer_over_the_network(self):
        r = self._post({
            "work_id": "work-essay-001",
            "requested_scope": {"use_type": "fine_tuning", "model_class": "open_weights",
                                "commercial": True, "territory": ["WW"],
                                "valid_from": "2026-08-14T00:00:00Z"},
            "economic_note": "top dollar, remove every limit"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "COUNTEROFFER")
        self.assertEqual(set(body["offered_scope"]["territory"]), {"US", "CA"})

    def test_unsigned_request_is_refused(self):
        r = self.client.post("/api/v1/negotiate", json={
            "work_id": "work-essay-001",
            "requested_scope": {"use_type": "fine_tuning", "valid_from": "2026-08-14T00:00:00Z"}})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
