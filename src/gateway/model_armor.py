import re
from typing import Dict, Any, Tuple
from pydantic import BaseModel

class InjectionDetectionResult(BaseModel):
    injection_detected: bool
    pattern_matched: str = ""
    original_bytes: bytes
    stored_bytes: bytes  # MUST be byte-identical to original_bytes (HOD-313 / Correction 2)
    proceed_under_original_scope: bool = True

class ModelArmor:
    """
    Model Armor (HOD-313).
    Inspects untrusted post-extraction bytes of inbound buyer scope documents.
    
    CRITICAL PRD REQUIREMENT (Correction 2):
    Model Armor MUST NOT modify or strip the inbound document!
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

        detected = False
        matched_pattern = ""

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text):
                detected = True
                matched_pattern = pattern
                break

        # Stored bytes MUST remain byte-identical to original raw_bytes (No stripping or rewriting!)
        stored_bytes = raw_bytes

        return InjectionDetectionResult(
            injection_detected=detected,
            pattern_matched=matched_pattern,
            original_bytes=raw_bytes,
            stored_bytes=stored_bytes,
            proceed_under_original_scope=True
        )
