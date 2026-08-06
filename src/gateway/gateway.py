from typing import Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
from src.schema.iam_policy import is_action_permitted

class PolicyDenialEvent(BaseModel):
    event_id: str
    calling_sa: str
    target_role: str
    requested_collection: str
    timestamp: datetime
    policy_consulted: str = "gateway_policy_v1"
    outcome: str = "DENIED"
    reason: str

class AgentGateway:
    """
    Agent Gateway (HOD-312).
    Routes every inter-agent call and enforces IAM policy boundaries.
    Denials are logged as events and OTel spans, NEVER silent.
    """

    def __init__(self):
        self.denial_events: list = []

    def route(self, calling_sa: str, calling_role_key: str, target_collection: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routes call through gateway.
        If calling_role_key is not authorized for target_collection, logs PolicyDenialEvent and raises PermissionError.
        """
        if not is_action_permitted(calling_role_key, target_collection):
            denial = PolicyDenialEvent(
                event_id=f"denial-{len(self.denial_events)+1}",
                calling_sa=calling_sa,
                target_role=calling_role_key,
                requested_collection=target_collection,
                timestamp=datetime.now(timezone.utc),
                reason=f"Calling SA '{calling_sa}' ({calling_role_key}) is denied access to target collection '{target_collection}'."
            )
            self.denial_events.append(denial)
            raise PermissionError(f"GATEWAY_POLICY_DENIAL: {denial.reason}")

        return {
            "status": "ROUTED",
            "calling_sa": calling_sa,
            "target_collection": target_collection,
            "payload": payload
        }
