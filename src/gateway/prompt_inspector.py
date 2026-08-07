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
    Prompt Inspector (HOD-313).
    Inspects untrusted post-extraction bytes of inbound buyer scope documents using local regex.
    
    CRITICAL PRD REQUIREMENT (Correction 2):
    Prompt Inspector MUST NOT modify or strip the inbound document!
    Emits an InjectionDetected event + anomaly item in Firestore & OTel trace,
    and the request PROCEEDS under its original validated scope.
    The stored inbound document MUST remain BYTE-IDENTICAL to what was received from the counterparty.
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
