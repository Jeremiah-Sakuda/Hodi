from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from src.schema.evidence import EvidenceRecord, CLAIM_LIMIT_LITERAL
from src.evidence.gemma_triage import GemmaTriageEngine
from src.evidence.overclaim_lint import OverclaimLint

class EvidenceEngine:
    """
    Evidence Engine (HOD-320).
    Processes crawler logs, canary strings, verbatim matches, and redistribution signals.
    Emits typed EvidenceRecords across 4 distinct honest evidence classes.
    No cross-class aggregation, scoring, or ordering.
    """

    def __init__(self):
        self.gemma_triage = GemmaTriageEngine()
        self.lint = OverclaimLint()
        self._records_by_class: Dict[str, List[EvidenceRecord]] = {
            "crawler_access": [],
            "canary_hit": [],
            "verbatim_match": [],
            "redistribution": []
        }

    def process_crawler_access(self, raw_access_record: Dict[str, Any]) -> Optional[EvidenceRecord]:
        """Triages crawler access record and emits a crawler_access EvidenceRecord if classified as bot."""
        triage_res = self.gemma_triage.triage_record(raw_access_record)
        if triage_res != "bot":
            return None

        record_id = raw_access_record.get("record_id", f"ev-crawl-{len(self._records_by_class['crawler_access'])+1}")
        work_id = raw_access_record.get("work_id", "work-essay-001")
        ua = raw_access_record.get("user_agent", "unknown")
        
        detail_text = f"Bot user-agent '{ua}' fetched work endpoint."
        self.lint.lint_text(detail_text)

        ev = EvidenceRecord(
            evidence_id=record_id,
            work_id=work_id,
            class_name="crawler_access",
            observed_at=datetime.now(timezone.utc),
            source_uri=raw_access_record.get("path", "/works/essay-001"),
            detail=detail_text,
            claim_limit=CLAIM_LIMIT_LITERAL
        )
        self._records_by_class["crawler_access"].append(ev)
        return ev

    def process_canary_hit(self, canary_string: str, work_id: str, found_uri: str) -> EvidenceRecord:
        """Emits a canary_hit EvidenceRecord."""
        record_id = f"ev-canary-{len(self._records_by_class['canary_hit'])+1}"
        detail_text = f"Planted canary string '{canary_string}' detected at third-party URI."
        self.lint.lint_text(detail_text)

        ev = EvidenceRecord(
            evidence_id=record_id,
            work_id=work_id,
            class_name="canary_hit",
            observed_at=datetime.now(timezone.utc),
            source_uri=found_uri,
            detail=detail_text,
            claim_limit=CLAIM_LIMIT_LITERAL
        )
        self._records_by_class["canary_hit"].append(ev)
        return ev

    def process_verbatim_match(self, prompt: str, generated_output: str, work_id: str, source_uri: str) -> EvidenceRecord:
        """
        Emits a verbatim_match EvidenceRecord.
        Note: verbatim_match depends on external model output surfaces.
        """
        record_id = f"ev-verb-{len(self._records_by_class['verbatim_match'])+1}"
        detail_text = f"Verbatim text string match observed in model completion output."
        self.lint.lint_text(detail_text)

        ev = EvidenceRecord(
            evidence_id=record_id,
            work_id=work_id,
            class_name="verbatim_match",
            observed_at=datetime.now(timezone.utc),
            source_uri=source_uri,
            detail=detail_text,
            claim_limit=CLAIM_LIMIT_LITERAL
        )
        self._records_by_class["verbatim_match"].append(ev)
        return ev

    def process_redistribution(self, work_id: str, mirror_uri: str) -> EvidenceRecord:
        """Emits a redistribution EvidenceRecord."""
        record_id = f"ev-redis-{len(self._records_by_class['redistribution'])+1}"
        detail_text = f"Unlicensed redistribution of registered work observed at mirror URI."
        self.lint.lint_text(detail_text)

        ev = EvidenceRecord(
            evidence_id=record_id,
            work_id=work_id,
            class_name="redistribution",
            observed_at=datetime.now(timezone.utc),
            source_uri=mirror_uri,
            detail=detail_text,
            claim_limit=CLAIM_LIMIT_LITERAL
        )
        self._records_by_class["redistribution"].append(ev)
        return ev

    def get_records_by_class(self, evidence_class: str) -> List[EvidenceRecord]:
        """Returns records for ONE specific evidence class independently. Never merges or scores."""
        return self._records_by_class.get(evidence_class, [])
