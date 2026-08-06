from typing import Literal, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

EvidenceClass = Literal["crawler_access", "canary_hit", "verbatim_match", "redistribution"]

CLAIM_LIMIT_LITERAL = "This record does not assert training-set membership."

class EvidenceRecord(BaseModel):
    evidence_id: str
    work_id: str
    class_name: EvidenceClass = Field(..., alias="class")
    observed_at: datetime
    source_uri: str
    detail: str
    claim_limit: Literal["This record does not assert training-set membership."] = CLAIM_LIMIT_LITERAL
    metadata: Optional[Dict[str, str]] = None

    model_config = {
        "extra": "forbid",
        "populate_by_name": True
    }

    @model_validator(mode="after")
    def validate_no_numeric_values_in_record(self):
        """Rejects any numeric values in payload, details, or metadata."""
        for field_name, value in self.__dict__.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                raise ValueError(
                    f"Honesty Invariant Violation: EvidenceRecord field '{field_name}' contains numeric value {value}. "
                    "Evidence classes cannot carry numeric scores, totals, or ranks."
                )
        if self.metadata:
            for k, v in self.metadata.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    raise ValueError(
                        f"Honesty Invariant Violation: EvidenceRecord metadata key '{k}' contains numeric value {v}."
                    )
        return self
