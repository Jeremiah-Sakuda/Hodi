import unittest
from src.schema.work import create_work, Work, ControlProof
import subprocess
from src.schema.verification import (UnsignedCommitError, UnverifiableMethodError,
                                     substantiate)
from src.schema.verification import (
    verify_dns_txt,
    verify_well_known_file,
    verify_signed_commit,
    verify_platform_oauth
)

class TestWorkVerification(unittest.TestCase):

    def test_verified_control_requires_control_proof(self):
        """HOD-105 AC: A registration without completed proof cannot reach verified_control."""
        with self.assertRaises(ValueError) as ctx:
            create_work(
                work_id="work-test-01",
                artist_id="artist-jeremiah",
                medium="prose",
                uri="https://medium.com/@jeremiah/essay-01",
                content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                control_tier="verified_control",  # Missing control_proof!
                title="Test Essay",
                description="Test description",
                published_at="2026-08-01T00:00:00Z",
                control_proof=None
            )
        self.assertIn("HOD-105", str(ctx.exception))

    def test_asserted_control_tier_without_proof_succeeds(self):
        """Works registered as 'asserted' do not require proof."""
        work = create_work(
            work_id="work-asserted-01",
            artist_id="artist-jeremiah",
            medium="audio",
            uri="https://hodi.dev/audio/bass-improv-01",
            content_hash="8f92a1b3c4d7e2f1a6b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0",
            control_tier="asserted",
            title="Asserted Bass Track",
            description="Electric bass solo track without verified DNS/OAuth proof",
            published_at="2026-08-02T00:00:00Z",
            control_proof=None
        )
        self.assertEqual(work.control_tier, "asserted")
        self.assertIsNone(work.control_proof)



    def test_the_three_unwired_methods_refuse_rather_than_mint(self):
        """HOD-748 hardened one verifier of four; these are the other three.

        `verify_dns_txt`, `verify_well_known_file` and `verify_platform_oauth`
        each validated that their arguments were non-empty and then returned a
        ControlProof carrying `status: "verified"`. Nothing resolved a TXT
        record, fetched a token, or exchanged an OAuth code — and three tests in
        this file asserted that behaviour as correct.

        They refuse now. Wiring them is real work; claiming them was not.
        """
        cases = (
            (verify_dns_txt, dict(domain="example.com", record_name="_hodi",
                                  expected_token="tok")),
            (verify_well_known_file, dict(target_url="https://example.com/.well-known/hodi-proof.json",
                                          expected_token="tok")),
            (verify_platform_oauth, dict(platform="github", account_id="1",
                                         account_handle="someone")),
        )
        for fn, kwargs in cases:
            with self.subTest(fn.__name__):
                with self.assertRaises(UnverifiableMethodError):
                    fn(**kwargs)

    def test_substantiate_never_promotes_a_proof_it_cannot_check(self):
        """The dispatcher production code calls. Judge E's exact payload."""
        verified, reason = substantiate({
            "method": "dns", "verified_at": "1999-01-01",
            "evidence_uri": "https://not-a-real-domain.invalid/whatever"})
        self.assertFalse(verified)
        self.assertIn("ASSERTED", reason)

        for method in ("well_known_file", "platform_oauth", "signed_commit", "nonsense"):
            with self.subTest(method):
                ok, _ = substantiate({"method": method, "evidence_uri": "https://x.invalid"})
                self.assertFalse(ok, f"{method} minted a verified tier from bare arguments")

    def test_signed_commit_proof_is_refused_for_an_unsigned_commit(self):
        """THIS TEST USED TO ASSERT THE BUG (HOD-748).

        It called `verify_signed_commit` with the SHA
        `7639226a1b2c3d4e5f60123456789abcdef01234` — which is not a commit in
        this repository or any other; it is the canary string with hex glued on
        — and asserted that a `verified_control` work came back. It did, because
        the function checked only that its arguments were non-empty and then
        restated them as a proof.

        So the strongest ownership claim in the system was verified by a
        function that verified nothing, guarded by a test that fed it a
        fictitious commit and called the result proof. The repository has never
        had a signed commit: `git log --format=%G?` reports `N` for all 99.
        """
        with self.assertRaises(UnsignedCommitError):
            verify_signed_commit(
                repo_uri="https://github.com/Jeremiah-Sakuda/Hodi",
                commit_sha="7639226a1b2c3d4e5f60123456789abcdef01234",
                author_identity="jeremiahsomoine@gmail.com",
            )

    def test_a_real_but_unsigned_commit_is_also_refused(self):
        """The fictitious SHA above could be refused merely for not existing.
        This one exists in this repository and is unsigned, which is the state
        that actually shipped."""
        head = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        self.assertTrue(head, "could not read HEAD; this guard would be vacuous")
        with self.assertRaises(UnsignedCommitError) as caught:
            verify_signed_commit(
                repo_uri="https://github.com/Jeremiah-Sakuda/Hodi",
                commit_sha=head,
                author_identity="jeremiahsomoine@gmail.com",
            )
        self.assertIn("no good signature", str(caught.exception))

    def test_a_verified_tier_without_a_stored_proof_is_downgraded_on_READ(self):
        """The schema forbids constructing it; nothing checked it on read.

        The manifest merges a persisted registry row with the committed seed.
        The registry row for `work-repo-001` carried `control_tier`; the seed
        carried the `control_proof`. Removing the unearned proof from the seed
        therefore left the LIVE manifest serving a `verified_control` work with
        no proof at all — the exact state `create_work()` exists to make
        unconstructible, reached by reading rather than writing.
        """
        from src.evidence_service.main import _tier_the_evidence_supports

        row = {"work_id": "w-x", "control_tier": "verified_control"}
        served = _tier_the_evidence_supports(row)
        self.assertEqual(served["control_tier"], "asserted")
        self.assertEqual(served["control_tier_downgraded_from"], "verified_control")
        self.assertIn("no stored control_proof", served["control_tier_downgraded_reason"])

        # A row that DOES carry a proof is untouched — the check must not
        # flatten every tier to `asserted` and call that honesty.
        with_proof = {"work_id": "w-y", "control_tier": "verified_control",
                      "control_proof": {"method": "dns", "verified_at": "2026-08-25T00:00:00Z"}}
        self.assertEqual(_tier_the_evidence_supports(with_proof)["control_tier"],
                         "verified_control")

    def test_the_served_manifest_claims_no_unearned_verified_tier(self):
        """The seed the deployed service returns must not out-claim the proof
        it can produce. `work-repo-001` sat at `verified_control` on this
        function's output until 2026-08-25."""
        from fastapi.testclient import TestClient
        from src.evidence_service.main import app

        payload = TestClient(app, raise_server_exceptions=False).get("/works").json()
        works = payload.get("works", payload if isinstance(payload, list) else [])
        self.assertTrue(works, "the manifest served no works; this guard would be vacuous")
        for work in works:
            if work.get("control_tier") == "verified_control":
                proof = work.get("control_proof") or {}
                self.assertNotEqual(
                    proof.get("method"), "signed_commit",
                    f"{work['work_id']} claims verified_control by signed commit, and no "
                    "commit in this repository is signed")

