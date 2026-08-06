from typing import Dict, Any, Optional
from src.schema.iam_policy import AGENT_SA_MAP, is_action_permitted

class BaseAgent:
    """Base class for all Fleet Agents enforcing IAM boundary checks."""
    
    def __init__(self, role_key: str):
        if role_key not in AGENT_SA_MAP:
            raise ValueError(f"Unknown agent role key: {role_key}")
        self.role_key = role_key
        self.sa_info = AGENT_SA_MAP[role_key]
        self.sa_email = self.sa_info["sa_email"]
        self.role_name = self.sa_info["role_name"]

    def can_access_collection(self, collection_name: str) -> bool:
        """Returns True if this agent SA is authorized to access the given collection."""
        return is_action_permitted(self.role_key, collection_name)

    def access_collection(self, collection_name: str) -> Dict[str, Any]:
        """Simulates collection read/write with IAM permission check."""
        if not self.can_access_collection(collection_name):
            raise PermissionError(
                f"PERMISSION_DENIED: Service account '{self.sa_email}' ({self.role_name}) "
                f"is denied access to collection '{collection_name}' under IAM conflict policy."
            )
        return {"status": "SUCCESS", "collection": collection_name, "sa": self.sa_email}
