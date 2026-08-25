"""
tests/test_oidc_audience_and_debug_cap.py — two deployed-surface defects
(HOD-743, HOD-744).

1. THE OIDC ROUTES DID NOT CHECK WHO THE TOKEN WAS FOR.
   `verify_oauth2_token(token, Request())` with no audience verifies Google's
   signature and the caller's identity — and NOT that the token was minted for
   this service. Any Google-signed ID token the same identity could obtain, for
   any other audience, satisfied every check `/internal/accrual_audit` and the
   domain-operation routes made. `caller_identity.from_oidc()` had always passed
   an audience, with a paragraph explaining why; it is not on the deployed path,
   so the explanation was in the repository and the check was not in the service.

   The fix has to accept a SET, because the two legitimate callers mint
   different and equally correct audiences — Cloud Scheduler the full target URL
   including path, the front door the service root. Pinning one would have 403'd
   a caller doing exactly the right thing, and the scheduled audit is a
   capability this project reports as verified.

2. THE PUBLIC BOUNDARY-PROOF ENDPOINT ECHOED AN UNBOUNDED CORPUS.
   It is public on purpose, so a reviewer can check the cross-buyer boundary
   without credentials. But it returned every document the demo counterparty
   holds, and that set grows with every recorded take — 6 documents, then 16,
   then 130. The proof is one permitted read and two refusals; it was never the
   volume.
"""

import os
import unittest

from src.api import buyer_api


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeRequest:
    def __init__(self, path, base="http://0.0.0.0:8080/"):
        self.url = _FakeURL(path)
        self.base_url = base


class OidcAudienceIsCheckedTest(unittest.TestCase):

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        from src.evidence_service import main
        self.main = main

    def test_the_scheduler_audience_is_accepted(self):
        """
        Read from the live job config: Cloud Scheduler mints the FULL target
        URL, path included. Rejecting it would break a scheduled capability
        this project reports as verified.
        """
        allowed = self.main.expected_oidc_audiences(_FakeRequest("/internal/accrual_audit"))
        self.assertIn(f"{self.main.CANONICAL_RUN_DOMAIN}/internal/accrual_audit", allowed)

    def test_the_service_root_audience_is_accepted(self):
        """The front door mints the service root when calling a domain workload."""
        allowed = self.main.expected_oidc_audiences(_FakeRequest("/internal/domain/read"))
        self.assertIn(self.main.CANONICAL_RUN_DOMAIN, allowed)

    def test_a_foreign_audience_is_not_accepted(self):
        allowed = self.main.expected_oidc_audiences(_FakeRequest("/internal/accrual_audit"))
        for foreign in ("https://example.com",
                        "https://some-other-service.a.run.app",
                        "https://hodi-evidence-endpoint-406699565497.us-central1.run.app.evil.test"):
            self.assertNotIn(foreign, allowed)

    def test_the_container_bind_address_alone_does_not_define_the_audience(self):
        """
        uvicorn runs without --proxy-headers, so `request.base_url` reports the
        container's own bind address. Deriving the audience only from the
        request would compare a public token against a private URL and refuse
        every legitimate caller.
        """
        allowed = self.main.expected_oidc_audiences(_FakeRequest("/internal/accrual_audit"))
        public = [a for a in allowed if a.startswith("https://")]
        self.assertTrue(public, "no public audience is accepted; every real caller would be 403'd")

    def test_a_token_for_another_audience_is_REFUSED(self):
        """
        Behavioural, not textual. An earlier version of this file asserted only
        that the source mentioned `claims.get("aud")` — and a mutation that
        replaced the refusal with `if False:` passed it, because the string was
        still there. A guard that reads the code instead of running it is the
        defect class this repository is built around.
        """
        from unittest import mock
        from fastapi import HTTPException

        foreign = {"aud": "https://some-other-service.a.run.app",
                   "email": "attacker@example.com", "email_verified": True}
        with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=foreign):
            with self.assertRaises(HTTPException) as caught:
                self.main._verified_oidc_claims(
                    _FakeRequest("/internal/accrual_audit"), "any-token")
        self.assertEqual(caught.exception.status_code, 403)

    def test_a_token_for_THIS_service_is_accepted(self):
        """The other half: a correct caller must still get through."""
        from unittest import mock

        good = {"aud": f"{self.main.CANONICAL_RUN_DOMAIN}/internal/accrual_audit",
                "email": "scheduler@example.com", "email_verified": True}
        with mock.patch("google.oauth2.id_token.verify_oauth2_token", return_value=good):
            claims = self.main._verified_oidc_claims(
                _FakeRequest("/internal/accrual_audit"), "any-token")
        self.assertEqual(claims["aud"], good["aud"])

    def test_both_deployed_verifiers_go_through_the_audience_check(self):
        import inspect
        src = inspect.getsource(self.main)
        self.assertEqual(
            src.count("_verified_oidc_claims(request, token)"), 2,
            "both OIDC verifiers must check the audience; a bare "
            "verify_oauth2_token(token, Request()) call has come back")
        body = src[src.index("def _verified_oidc_claims"):]
        body = body[:body.index("\ndef ")]
        self.assertIn("claims.get(\"aud\"", body)


class TheDebugEndpointDoesNotPublishTheCorpusTest(unittest.TestCase):

    def test_the_sample_limit_is_small_and_declared(self):
        self.assertLessEqual(buyer_api.DEBUG_SAMPLE_LIMIT, 5)
        self.assertGreaterEqual(buyer_api.DEBUG_SAMPLE_LIMIT, 1,
                                "returning nothing would remove the evidence that the scoped read "
                                "is permitted, which is half the proof")

    def test_the_endpoint_returns_a_capped_sample_and_the_true_count(self):
        import inspect
        src = inspect.getsource(buyer_api)
        block = src[src.index("if req.attack_type == \"valid_read\""):]
        block = block[:block.index("elif req.attack_type")]
        self.assertIn("docs_returned", block,
                      "the TRUE count must survive the cap — it is what proves the read succeeded")
        self.assertIn("DEBUG_SAMPLE_LIMIT", block)
        self.assertNotIn('"docs": jsonable_encoder(docs)', block,
                         "the endpoint is publishing the whole corpus again")


if __name__ == "__main__":
    unittest.main()
