from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from src.schema.grant_event import GrantEvent

class RevocationNotice(BaseModel):
    grant_id: str = Field(..., description="The ID of the grant being revoked.")
    counterparty_id: str = Field(..., description="The opaque identifier for the buyer.")
    revoked_at: datetime = Field(..., description="Timestamp of revocation.")
    notice_text: str = Field(..., description="The text of the termination notice.")

class RevocationReceipt(BaseModel):
    revocation_id: str = Field(..., description="Unique receipt ID for the revocation.")
    grant_id: str = Field(..., description="The ID of the grant that was revoked.")
    counterparty_id: str = Field(..., description="The opaque identifier for the buyer.")
    revoked_at: datetime = Field(..., description="Timestamp of revocation.")
    signature: str = Field(..., description="Cryptographic signature of the revocation notice.")
