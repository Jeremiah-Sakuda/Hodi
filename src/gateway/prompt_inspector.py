import os
import re
from typing import Dict, Any, Tuple
from pydantic import BaseModel

class InjectionDetectionResult(BaseModel):
    injection_detected: bool
    pattern_matched: str = ""
    inspector_engine: str
    original_bytes: bytes
    stored_bytes: bytes  # MUST be byte-identical to original_bytes (HOD-313 / Correction 2)
    proceed_under_original_scope: bool = True

class PromptInspector:
    """
    Prompt Inspector (HOD-313) — a DETERMINISTIC FIRST-PASS INJECTION INDICATOR,
    labelled `local_regex_inspector` everywhere it appears.

    Positioning, stated so no reviewer has to infer it: this is a local regex
    over an enumerated pattern list, NOT a general prompt-injection defense and
    NOT the managed Model Armor guardrail (that API was in restricted preview
    and returned 403 for this project, so the claim was pulled — see BUILD-LOG
    2026-08-07). A semantically-equivalent paraphrase — "disregard everything
    that preceded this" — can evade the literal patterns, and that is expected
    of a first-pass indicator: it flags the obvious payloads and the request
    PROCEEDS under its original scope regardless. The load-bearing guarantee is
    NOT that the regex catches everything; it is that detection can never widen
    the licensable set, because the lattice decides permission and the document
    text is never an input to it.

    CRITICAL PRD REQUIREMENT (Correction 2):
    The inspector MUST NOT modify or strip the inbound document. It emits an
    InjectionDetected event + anomaly item and the request proceeds under its
    original validated scope; the stored inbound document remains BYTE-IDENTICAL
    to what the counterparty sent, so it can never become an evidentiary dispute
    over altered contractual input.
    """
    
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"system\s+prompt\s+override",
        r"grant\s+unlimited\s+commercial\s+rights",
        r"set\s+price\s+to\s+\$0",
        r"bypass\s+consent\s+policy"
    ]

    def inspect(self, raw_bytes: bytes) -> InjectionDetectionResult:
        try:
            text = raw_bytes.decode("utf-8", errors="ignore").lower()
        except Exception:
            text = ""

        detected, matched_pattern = self._regex_inspect(text)
        engine = "local_regex_inspector"

        return InjectionDetectionResult(
            injection_detected=detected,
            pattern_matched=matched_pattern,
            inspector_engine=engine,
            original_bytes=raw_bytes,
            stored_bytes=raw_bytes,
            proceed_under_original_scope=True
        )

    def _regex_inspect(self, text: str) -> Tuple[bool, str]:
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return True, f"Regex Match: {pattern}"
        return False, ""
