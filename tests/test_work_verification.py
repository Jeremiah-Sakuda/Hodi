import unittest
from src.schema.work import create_work, Work, ControlProof
import subprocess
from src.schema.verification import UnsignedCommitError
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

    def test_dns_txt_verification_proof(self):
        proof = verify_dns_txt(
            domain="hodi.dev",
            record_name="_hodi-challenge",
            expected_token="token-dns-12345"
        )
        self.assertEqual(proof.method, "dns")
        work = create_work(
            work_id="work-dns-01",
            artist_id="artist-jeremiah",
            medium="prose",
            uri="https://hodi.dev/essay/consent-rails",
            content_hash="a1b2c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123",
            control_tier="verified_control",
            title="Consent Rails Essay",
            description="Essay on creative consent",
            published_at="2026-08-03T00:00:00Z",
            control_proof=proof
        )
        self.assertEqual(work.control_tier, "verified_control")
        self.assertEqual(work.control_proof.method, "dns")

    def test_well_known_file_verification_proof(self):
        proof = verify_well_known_file(
            target_url="https://github.com/Jeremiah-Sakuda/Hodi/.well-known/hodi-proof.json",
            expected_token="token-wellknown-67890"
        )
        self.assertEqual(proof.method, "well_known_file")
        work = create_work(
            work_id="work-wk-01",
            artist_id="artist-jeremiah",
            medium="code",
            uri="https://github.com/Jeremiah-Sakuda/Hodi",
            content_hash="b2c3d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123a1",
            control_tier="verified_control",
            title="Hodi Core Repo",
            description="Hodi source repository",
            published_at="2026-08-04T00:00:00Z",
            control_proof=proof
        )
        self.assertEqual(work.control_tier, "verified_control")
        self.assertEqual(work.control_proof.method, "well_known_file")

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

    def test_platform_oauth_verification_proof(self):
        proof = verify_platform_oauth(
            platform="github",
            account_id="github-user-123456",
            account_handle="Jeremiah-Sakuda"
        )
        self.assertEqual(proof.method, "platform_oauth")
        work = create_work(
            work_id="work-oauth-01",
            artist_id="artist-jeremiah",
            medium="audio",
            uri="https://github.com/Jeremiah-Sakuda/Hodi/works/audio-001",
            content_hash="d4e5f60123456789abcdef0123456789abcdef0123456789abcdef0123a1b2c3",
            control_tier="verified_control",
            title="Bass Recordings Manifest",
            description="Audio stems verified via GitHub OAuth",
            published_at="2026-08-06T00:00:00Z",
            control_proof=proof
        )
        self.assertEqual(work.control_tier, "verified_control")

if __name__ == "__main__":
    unittest.main()
