from typing import Literal, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

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

class ScopeEvaluationResult(BaseModel):
    permitted: bool
    matching_grant_id: Optional[str] = None
    attribution_required: bool = False
    reason: str
