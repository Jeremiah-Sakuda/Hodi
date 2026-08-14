import unittest
from src.evidence.evidence_engine import EvidenceEngine
from src.schema.evidence import CLAIM_LIMIT_LITERAL

class TestEvidenceEngine(unittest.TestCase):
    """
    Evidence Engine Tests (HOD-320).
    Verifies 4 honest evidence classes, Gemma triage filtering, and claim_limit enforcement.
    """

    def setUp(self):
        self.engine = EvidenceEngine()

    def test_crawler_access_evidence_generation(self):
        """Gemma triage classifies GPTBot access as bot and emits crawler_access EvidenceRecord."""
        raw_rec = {
            "record_id": "crawl-001",
            "user_agent": "Mozilla/5.0 (compatible; GPTBot/1.0)",
            "work_id": "work-essay-001",
            "path": "/works/essay-001"
        }
        ev = self.engine.process_crawler_access(raw_rec)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.class_name, "crawler_access")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)

    def test_crawler_access_ignores_human(self):
        """Human user-agent access is ignored by Gemma triage and yields no EvidenceRecord."""
        raw_rec = {
            "record_id": "crawl-002",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0",
            "work_id": "work-essay-001"
        }
        ev = self.engine.process_crawler_access(raw_rec)
        self.assertIsNone(ev)

    def test_canary_hit_evidence_generation(self):
        """Emits canary_hit EvidenceRecord with claim_limit."""
        ev = self.engine.process_canary_hit(
            canary_string="HODI-CANARY-20260806-PROSE-9F81A2B3C4",
            work_id="work-essay-001",
            found_uri="https://unauthorized-scrape.com/dump.txt"
        )
        self.assertEqual(ev.class_name, "canary_hit")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)

    # The registered excerpt these tests match against — genuine text from
    # work-repo-001 (this repository), see fixtures/work_passages.json.
    REGISTERED_EXCERPT = ("Hodi is a governed fleet of institutional agents that administers "
                          "creative consent end to end: registering works with proof of control, "
                          "expressing scoped machine-readable terms")

    def test_verbatim_match_emitted_when_registered_text_actually_appears(self):
        """Positive: a real contiguous run of registered text produces a record."""
        ev = self.engine.process_verbatim_match(
            prompt="Complete the opening paragraph",
            generated_output=f"Sure! {self.REGISTERED_EXCERPT}, and so on.",
            work_id="work-repo-001",
            source_uri="https://api.model-provider.com/v1/completions"
        )
        self.assertIsNotNone(ev, "a genuine verbatim run must produce a record")
        self.assertEqual(ev.class_name, "verbatim_match")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)
        # The detail must describe THIS match, not a constant sentence.
        self.assertIn("contiguous run", ev.detail)
        self.assertIn(ev.metadata["matched_run_sha256"][:16], ev.detail)

    def test_verbatim_match_not_emitted_for_unrelated_output(self):
        """
        The assertion this file previously could not make. The old version passed
        generated_output="Verbatim essay excerpt" — sharing nothing with any
        registered work — and asserted a record WAS produced, blessing a method
        that read neither the prompt nor the output.
        """
        ev = self.engine.process_verbatim_match(
            prompt="Complete essay paragraph",
            generated_output="Verbatim essay excerpt",
            work_id="work-essay-001",
            source_uri="https://api.model-provider.com/v1/completions"
        )
        self.assertIsNone(ev, "unrelated output must NOT mint a verbatim_match record")

    def test_verbatim_match_not_emitted_for_a_paraphrase(self):
        """`verbatim` means exact. Similar-meaning text is not a verbatim match —
        which is why this check is deterministic and not a model."""
        ev = self.engine.process_verbatim_match(
            prompt="Describe the project",
            generated_output=("Hodi manages permissions for creative works using several "
                              "cooperating agents and a deterministic policy engine."),
            work_id="work-repo-001",
            source_uri="https://api.model-provider.com/v1/completions"
        )
        self.assertIsNone(ev, "a paraphrase must NOT mint a verbatim_match record")

    def test_redistribution_emitted_when_the_canary_is_present(self):
        """Positive: the planted canary actually appears in the mirrored content."""
        canary = "HODI-CANARY-20260806-CODE-7639226A1B"
        ev = self.engine.process_redistribution(
            work_id="work-repo-001",
            mirror_uri="https://mirror-site.com/repo-001",
            mirror_content=f"reposted without permission {canary} enjoy",
            canary_string=canary,
        )
        self.assertIsNotNone(ev)
        self.assertEqual(ev.class_name, "redistribution")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)

    def test_redistribution_not_emitted_without_observed_content(self):
        """
        The old signature was (work_id, mirror_uri) — no content parameter at
        all — so it could not verify a redistribution even in principle, yet
        emitted one every call. A URI alone is not an observation.
        """
        ev = self.engine.process_redistribution(
            work_id="work-essay-001",
            mirror_uri="https://mirror-site.com/essay-001"
        )
        self.assertIsNone(ev, "a bare URI must NOT mint a redistribution record")

if __name__ == "__main__":
    unittest.main()
