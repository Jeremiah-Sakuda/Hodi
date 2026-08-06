from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field, root_validator, model_validator

ControlTier = Literal["verified_control", "asserted", "disputed"]
ProofMethod = Literal["dns", "well_known_file", "signed_commit", "platform_oauth"]

class ControlProof(BaseModel):
    method: ProofMethod
    verified_at: str
    evidence_uri: str
    metadata: Optional[Dict[str, Any]] = None

class Work(BaseModel):
    work_id: str
    artist_id: str
    medium: Literal["prose", "code", "audio", "image", "video"]
    uri: str
    content_hash: str  # SHA-256 hash of content or manifest
    control_tier: ControlTier
    control_proof: Optional[ControlProof] = None
    title: str
    description: str
    published_at: str
    canary_string: Optional[str] = None
    canary_planted_at: Optional[str] = None

    @model_validator(mode='after')
    def validate_control_tier_has_proof(self):
        if self.control_tier == "verified_control" and self.control_proof is None:
            raise ValueError(
                "Invariant violation (HOD-105): A work cannot have control_tier='verified_control' without a valid control_proof."
            )
        return self

def create_work(
    work_id: str,
    artist_id: str,
    medium: str,
    uri: str,
    content_hash: str,
    control_tier: ControlTier,
    title: str,
    description: str,
    published_at: str,
    control_proof: Optional[ControlProof] = None,
    canary_string: Optional[str] = None,
    canary_planted_at: Optional[str] = None,
) -> Work:
    """
    Factory function ensuring no code path reaches control_tier='verified_control'
    without a valid stored control_proof.
    """
    if control_tier == "verified_control" and control_proof is None:
        raise ValueError(
            "Cannot assign 'verified_control' tier without a verified control_proof (HOD-105)."
        )
    return Work(
        work_id=work_id,
        artist_id=artist_id,
        medium=medium,
        uri=uri,
        content_hash=content_hash,
        control_tier=control_tier,
        control_proof=control_proof,
        title=title,
        description=description,
        published_at=published_at,
        canary_string=canary_string,
        canary_planted_at=canary_planted_at,
    )
