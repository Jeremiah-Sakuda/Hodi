from typing import Literal, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

UseType = Literal["training", "fine_tuning", "rag_retrieval", "human_reference", "synthesis"]
ModelClass = Literal["all_models", "open_weights", "proprietary_frontier"]

class Scope(BaseModel):
    use_type: UseType
    model_class: ModelClass = "all_models"
    commercial: bool = False
    attribution_required: bool = False
    territory: List[str] = Field(default_factory=lambda: ["WW"])
    valid_from: datetime
    valid_until: Optional[datetime] = None

    @field_validator("valid_from", "valid_until")
    @classmethod
    def _window_must_denote_instants(cls, v, info):
        """The same rule as GrantEvent.issued_at, for the same reason (HOD-747).

        A window bound without an offset makes `is_scope_current` and
        `scope_window_has_closed` server-local, so whether a licence is in force
        would depend on which machine asked."""
        from src.schema.grant_event import reject_naive
        return reject_naive(v, f"Scope.{info.field_name}")

    @model_validator(mode="after")
    def _interval_must_be_well_formed(self) -> "Scope":
        # A scope whose window ends before it begins is not a narrow scope, it
        # is a malformed one, and malformed inputs are refused at the boundary
        # (HTTP 422 on the API), never interpreted. Letting it through would
        # hand permits() an interval that contains nothing while LOOKING like a
        # bounded window — the evaluator would deny it for the wrong reason,
        # and a grant authored with it would be unsatisfiable silently.
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError(
                f"Malformed validity interval: valid_until ({self.valid_until.isoformat()}) "
                f"precedes valid_from ({self.valid_from.isoformat()})."
            )
        return self

class ScopeEvaluationResult(BaseModel):
    permitted: bool
    matching_grant_id: Optional[str] = None
    attribution_required: bool = False
    reason: str
