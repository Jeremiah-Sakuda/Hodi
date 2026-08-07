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

    def test_verbatim_match_evidence_generation(self):
        """Emits verbatim_match EvidenceRecord with claim_limit."""
        ev = self.engine.process_verbatim_match(
            prompt="Complete essay paragraph",
            generated_output="Verbatim essay excerpt",
            work_id="work-essay-001",
            source_uri="https://api.model-provider.com/v1/completions"
        )
        self.assertEqual(ev.class_name, "verbatim_match")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)

    def test_redistribution_evidence_generation(self):
        """Emits redistribution EvidenceRecord with claim_limit."""
        ev = self.engine.process_redistribution(
            work_id="work-essay-001",
            mirror_uri="https://mirror-site.com/essay-001"
        )
        self.assertEqual(ev.class_name, "redistribution")
        self.assertEqual(ev.claim_limit, CLAIM_LIMIT_LITERAL)

if __name__ == "__main__":
    unittest.main()
