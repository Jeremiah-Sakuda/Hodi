import unittest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.schema.evidence import EvidenceRecord, CLAIM_LIMIT_LITERAL
from src.schema.work import Work, create_work, ControlProof

class TestSchemaValidation(unittest.TestCase):
    """
    HOD-101 & HOD-105 Schema Validation Tests.
    Proves structural honesty invariants for EvidenceRecord and Work schemas.
    """

    def test_evidence_record_schema_cannot_express_numeric_fields(self):
        """
        Correction 4(b): Assert against EvidenceRecord model definition itself.
        Iterate field type annotations and assert NO field carries a numeric annotation (int, float).
        This guarantees the schema cannot express a numeric score even for uninstantiated fields.
        """
        numeric_types = (int, float)
        for field_name, field_info in EvidenceRecord.model_fields.items():
            annotation = field_info.annotation
            # Check annotation direct type or args
            self.assertNotIn(annotation, numeric_types, f"Field '{field_name}' carries numeric annotation {annotation}!")
            if hasattr(annotation, "__args__"):
                for arg in annotation.__args__:
                    self.assertNotIn(arg, numeric_types, f"Field '{field_name}' type argument carries numeric annotation {arg}!")

    def test_evidence_record_rejects_numeric_instantiation(self):
        """HOD-101 AC: An EvidenceRecord with a numeric field fails validation."""
        with self.assertRaises((ValueError, ValidationError)):
            EvidenceRecord(
                evidence_id="ev-01",
                work_id="work-01",
                class_name="crawler_access",
                observed_at=datetime.now(timezone.utc),
                source_uri="https://example.com/log",
                detail="Access log detail",
                score=0.95  # Extra numeric field forbidden!
            )

    def test_evidence_record_literal_claim_limit(self):
        """Every EvidenceRecord carries literal claim_limit string."""
        rec = EvidenceRecord(
            evidence_id="ev-01",
            work_id="work-01",
            class_name="crawler_access",
            observed_at=datetime.now(timezone.utc),
            source_uri="https://example.com/log",
            detail="Access log detail"
        )
        self.assertEqual(rec.claim_limit, CLAIM_LIMIT_LITERAL)

    def test_work_verified_control_without_proof_fails_validation(self):
        """HOD-101 / HOD-105 AC: Work with verified_control and no control_proof fails validation."""
        with self.assertRaises(ValueError):
            create_work(
                work_id="w1",
                artist_id="a1",
                medium="prose",
                uri="https://example.com",
                content_hash="hash123",
                control_tier="verified_control",  # Missing control_proof!
                title="Title",
                description="Desc",
                published_at="2026-08-01T00:00:00Z",
                control_proof=None
            )

    def test_work_asserted_tier_without_proof_succeeds(self):
        work = create_work(
            work_id="w2",
            artist_id="a1",
            medium="prose",
            uri="https://example.com",
            content_hash="hash123",
            control_tier="asserted",
            title="Title",
            description="Desc",
            published_at="2026-08-01T00:00:00Z",
            control_proof=None
        )
        self.assertEqual(work.control_tier, "asserted")
        self.assertIsNone(work.control_proof)

if __name__ == "__main__":
    unittest.main()
