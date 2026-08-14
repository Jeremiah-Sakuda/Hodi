from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from src.schema.evidence import EvidenceRecord, CLAIM_LIMIT_LITERAL
from src.evidence.gemma_triage import GemmaTriageEngine
from src.evidence.overclaim_lint import OverclaimLint
from src.evidence.verbatim_probe import (
    MIN_VERBATIM_RUN_TOKENS, contains_canary, longest_contiguous_run,
)

import json
from pathlib import Path

_PASSAGES_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "work_passages.json"


def registered_passages(work_id: str) -> List[Dict[str, str]]:
    """The protected excerpts a verbatim_match is checked against.

    A work with no registered passage yields NO record — the honest outcome.
    `Work` carries only a content_hash, so the text itself must be registered
    (fixtures/work_passages.json) for any comparison to be possible."""
    try:
        with open(_PASSAGES_PATH) as f:
            return json.load(f).get("passages", {}).get(work_id, [])
    except (OSError, ValueError):
        return []

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

    def process_verbatim_match(self, prompt: str, generated_output: str, work_id: str,
                               source_uri: str) -> Optional[EvidenceRecord]:
        """
        Emits a verbatim_match EvidenceRecord ONLY when a run of registered text
        of at least MIN_VERBATIM_RUN_TOKENS actually appears in `generated_output`.

        This method previously read neither `prompt` nor `generated_output` and
        emitted unconditionally — a check in name only, with a constant detail
        string. It now returns None when there is no run, which is the outcome
        the old implementation could not produce. `prompt` is retained because
        it is part of the observation's provenance; it is deliberately NOT
        matched against, since a match in the prompt would only establish that
        the operator supplied the text.
        """
        best = None
        for passage in registered_passages(work_id):
            run = longest_contiguous_run(passage.get("text", ""), generated_output)
            if run and (best is None or run.token_count > best[0].token_count):
                best = (run, passage)

        if best is None:
            return None

        run, passage = best
        record_id = f"ev-verb-{len(self._records_by_class['verbatim_match'])+1}"
        detail_text = (
            f"A {run.token_count}-token contiguous run of registered passage "
            f"'{passage.get('passage_id', 'unknown')}' appears in the observed model output "
            f"(matched-run sha256 {run.passage_sha256[:16]}; threshold "
            f"{MIN_VERBATIM_RUN_TOKENS} tokens). Co-occurrence of text only."
        )
        self.lint.lint_text(detail_text)

        ev = EvidenceRecord(
            evidence_id=record_id,
            work_id=work_id,
            class_name="verbatim_match",
            observed_at=datetime.now(timezone.utc),
            source_uri=source_uri,
            detail=detail_text,
            claim_limit=CLAIM_LIMIT_LITERAL,
            metadata={
                "matched_run_tokens": str(run.token_count),
                "matched_run_sha256": run.passage_sha256,
                "registered_passage_id": str(passage.get("passage_id", "unknown")),
            },
        )
        self._records_by_class["verbatim_match"].append(ev)
        return ev

    def process_redistribution(self, work_id: str, mirror_uri: str,
                               mirror_content: str = "",
                               canary_string: Optional[str] = None) -> Optional[EvidenceRecord]:
        """
        Emits a redistribution EvidenceRecord ONLY when the content served at
        `mirror_uri` actually carries the work: either the planted canary
        (exact containment) or a run of registered text at or above
        MIN_VERBATIM_RUN_TOKENS.

        This method previously took no content parameter at all — `(work_id,
        mirror_uri)` — so it could not have verified anything even in
        principle, yet emitted unconditionally. `mirror_content` and
        `canary_string` default to empty so existing callers do not break; with
        no content supplied the method now returns None rather than asserting a
        redistribution nobody observed.
        """
        basis = None
        if contains_canary(canary_string, mirror_content):
            basis = f"planted canary '{canary_string}' present in the content served at the mirror URI"
        else:
            for passage in registered_passages(work_id):
                run = longest_contiguous_run(passage.get("text", ""), mirror_content)
                if run:
                    basis = (f"a {run.token_count}-token contiguous run of registered passage "
                             f"'{passage.get('passage_id', 'unknown')}' present at the mirror URI "
                             f"(matched-run sha256 {run.passage_sha256[:16]})")
                    break

        if basis is None:
            return None

        record_id = f"ev-redis-{len(self._records_by_class['redistribution'])+1}"
        detail_text = (f"Registered work observed at a third-party mirror URI: {basis}. "
                       "Presence of the work at that URI only; licence status is not asserted here.")
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
