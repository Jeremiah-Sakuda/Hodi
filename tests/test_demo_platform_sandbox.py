"""
tests/test_demo_platform_sandbox.py — the platform sandbox (HOD-780): the
Studio and Market journeys keep the demo/real boundary and the honesty rules.

What these tests hold, in order of importance:

  1. THE BOUNDARY. Every write the two journeys perform lands in a `demo_*`
     collection — asserted directly against the gateway's write sink, not
     inferred from route names.
  2. THE DECISION IS NOT THE MODEL'S. The interpreter is stubbed to a typed
     scope here precisely because the decision must be a pure function of
     (declared terms × event log); these tests exercise that function through
     the real route.
  3. REVOCATION CLOSES THE OFFER. After the artist revokes, the SAME request
     that was granted is refused — read from the append-only log, so the fact
     survives instance restarts and cannot be un-set.
  4. REGISTRATION STORES A CLAIM. `content_stored` is False and only
     title/medium/size/sha256 are persisted — the platform never holds bytes.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.schema.scope import Scope
from tests.offline_env import force_offline

VALID_SHA = "a" * 64


def _scope(use_type="fine_tuning", commercial=False, attribution=True):
    return Scope(use_type=use_type, model_class="open_weights", commercial=commercial,
                 attribution_required=attribution, territory=["US"],
                 valid_from=datetime.now(timezone.utc))


def _register_body(**over):
    body = {"title": "Harbor Lights EP", "medium": "audio", "sha256": VALID_SHA,
            "size_bytes": 1024, "offered_use_types": ["fine_tuning"],
            "commercial_ok": False, "attribution_required": True}
    body.update(over)
    return body


class PlatformSandboxTest(unittest.TestCase):
    def setUp(self):
        force_offline(self)
        import os
        prior = os.environ.get("HODI_SIGNING")
        os.environ["HODI_SIGNING"] = "ephemeral"
        self.addCleanup(lambda: os.environ.__setitem__("HODI_SIGNING", prior)
                        if prior is not None else os.environ.pop("HODI_SIGNING", None))
        # A fresh gateway (and empty write sink) per test.
        import src.api.demo_sandbox as sandbox
        sandbox._GATEWAY = None
        sandbox._sid_signatures.clear()
        sandbox._sid_interprets.clear()
        self.sandbox = sandbox
        from src.evidence_service.main import app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.sid = self.client.post("/demo/api/session").json()["session"]

    def _interpret(self, scope):
        return patch("src.llm.scope_interpreter.ScopeInterpreter.interpret",
                     return_value=scope)

    def _ask(self, work_id, scope, text="May we fine-tune on this?"):
        with self._interpret(scope):
            return self.client.post(f"/demo/api/{self.sid}/request-license",
                                    json={"work_id": work_id, "text": text})

    # -- works ---------------------------------------------------------------

    def test_session_starts_with_three_seeded_works(self):
        j = self.client.get(f"/demo/api/{self.sid}/works").json()
        self.assertEqual(len(j["works"]), 3)
        self.assertTrue(all(w["work_id"].startswith(f"demo-{self.sid}") for w in j["works"]))

    def test_registration_stores_a_claim_never_content(self):
        r = self.client.post(f"/demo/api/{self.sid}/works", json=_register_body())
        self.assertEqual(r.status_code, 200)
        work = r.json()["work"]
        self.assertFalse(work["content_stored"])
        self.assertNotIn("content", work)
        # and it appears in the listing
        j = self.client.get(f"/demo/api/{self.sid}/works").json()
        self.assertIn(work["work_id"], [w["work_id"] for w in j["works"]])

    def test_registration_rejects_malformed_claims(self):
        for bad in (_register_body(sha256="zz"), _register_body(medium="hologram"),
                    _register_body(offered_use_types=["mind_reading"]),
                    _register_body(offered_use_types=[]),
                    _register_body(title="   "), _register_body(size_bytes=-1)):
            r = self.client.post(f"/demo/api/{self.sid}/works", json=bad)
            self.assertEqual(r.status_code, 422, f"accepted malformed claim: {bad}")

    # -- the market decision -------------------------------------------------

    def test_offered_use_grants_and_appends_a_real_event(self):
        s1 = f"demo-{self.sid}-s1"   # offers fine_tuning
        r = self._ask(s1, _scope("fine_tuning"))
        j = r.json()
        self.assertEqual(j["decision"], "granted")
        self.assertTrue(j["binds"])
        self.assertEqual(j["grant"]["work_id"], s1)
        events = self.sandbox._read_events(self.sandbox._gateway(), s1)
        self.assertEqual([e.kind for e in events], ["granted"])

    def test_wider_than_offered_is_refused_and_appends_nothing(self):
        s1 = f"demo-{self.sid}-s1"   # offers fine_tuning; training is WIDER
        j = self._ask(s1, _scope("training")).json()
        self.assertEqual(j["decision"], "refused")
        self.assertTrue(any("not inside" in r for r in j["reasons"]))
        self.assertEqual(self.sandbox._read_events(self.sandbox._gateway(), s1), [])

    def test_commercial_against_noncommercial_terms_is_refused(self):
        j = self._ask(f"demo-{self.sid}-s1", _scope("fine_tuning", commercial=True)).json()
        self.assertEqual(j["decision"], "refused")
        self.assertTrue(any("non-commercially" in r for r in j["reasons"]))

    def test_declining_required_attribution_is_refused(self):
        j = self._ask(f"demo-{self.sid}-s1", _scope("fine_tuning", attribution=False)).json()
        self.assertEqual(j["decision"], "refused")
        self.assertTrue(any("attribution" in r for r in j["reasons"]))

    def test_narrower_use_is_contained_in_the_offer(self):
        # s2 offers rag_retrieval; human_reference is narrower — granted.
        j = self._ask(f"demo-{self.sid}-s2", _scope("human_reference")).json()
        self.assertEqual(j["decision"], "granted")

    # -- revocation closes the offer ----------------------------------------

    def test_revoking_refuses_the_same_request_afterwards(self):
        s1 = f"demo-{self.sid}-s1"
        self.assertEqual(self._ask(s1, _scope("fine_tuning")).json()["decision"], "granted")
        r = self.client.post(f"/demo/api/{self.sid}/revoke",
                             json={"work_id": s1, "revoked_use_type": "fine_tuning"})
        self.assertEqual(r.status_code, 200)
        j = self._ask(s1, _scope("fine_tuning")).json()
        self.assertEqual(j["decision"], "refused")
        self.assertTrue(any("offer is closed" in r for r in j["reasons"]))

    def test_revoke_refuses_a_work_from_another_session(self):
        r = self.client.post(f"/demo/api/{self.sid}/revoke",
                             json={"work_id": "demo-someoneelse-s1",
                                   "revoked_use_type": "training"})
        self.assertEqual(r.status_code, 403)

    # -- the boundary, asserted against the sink -----------------------------

    def test_every_platform_write_lands_in_a_demo_collection(self):
        s1 = f"demo-{self.sid}-s1"
        self.client.post(f"/demo/api/{self.sid}/works", json=_register_body())
        self._ask(s1, _scope("fine_tuning"))
        self.client.post(f"/demo/api/{self.sid}/revoke",
                         json={"work_id": s1, "revoked_use_type": "fine_tuning"})
        touched = set(self.sandbox._gateway()._offline_writes.keys())
        self.assertTrue(touched, "the journey should have written something")
        offenders = {c for c in touched if not c.startswith("demo_")}
        self.assertEqual(offenders, set(),
                         f"platform journey wrote outside demo_*: {offenders}")

    def test_grants_ledger_shows_history_and_notices_after_revocation(self):
        s1 = f"demo-{self.sid}-s1"
        self._ask(s1, _scope("fine_tuning"))
        self.client.post(f"/demo/api/{self.sid}/revoke",
                         json={"work_id": s1, "revoked_use_type": "fine_tuning"})
        j = self.client.get(f"/demo/api/{self.sid}/grants").json()
        row = next(w for w in j["works"] if w["work"]["work_id"] == s1)
        kinds = [e["kind"] for e in row["events"]]
        self.assertIn("granted", kinds)
        self.assertIn("revoked", kinds)
        self.assertEqual(row["active"], [])
        self.assertTrue(row["notices"], "the signed notice should be in the ledger")


if __name__ == "__main__":
    unittest.main()
