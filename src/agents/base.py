from typing import Dict, Any, Optional
from src.schema.iam_policy import AGENT_SA_MAP, is_action_permitted, get_action_permission

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

    def access_collection(self, collection_name: str, filters: Optional[Dict[str, Any]] = None,
                          session_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Collection read/write with the IAM permission check applied — the SAME
        policy data and the SAME filter rules the Gateway enforces, so an agent
        cannot reach data by calling itself instead of routing through the
        Gateway.
        """
        permitted, required_filter_key = get_action_permission(self.role_key, collection_name)
        if not permitted:
            raise PermissionError(
                f"PERMISSION_DENIED: Service account '{self.sa_email}' ({self.role_name}) "
                f"is denied access to collection '{collection_name}' under IAM conflict policy."
            )

        if required_filter_key:
            if not filters or required_filter_key not in filters:
                raise PermissionError(
                    f"PERMISSION_DENIED: Service account '{self.sa_email}' ({self.role_name}) "
                    f"MUST scope its query to '{required_filter_key}' for collection '{collection_name}'."
                )
            if session_context and required_filter_key in session_context:
                if filters[required_filter_key] != session_context[required_filter_key]:
                    raise PermissionError(
                        f"PERMISSION_DENIED: Service account '{self.sa_email}' ({self.role_name}) "
                        f"attempted to read '{required_filter_key}'='{filters[required_filter_key]}' "
                        f"outside of session context '{session_context[required_filter_key]}'."
                    )

        # The enforced filter is returned so callers and tests can assert that
        # scoping actually happened, rather than inferring it from a path string.
        return {
            "status": "SUCCESS",
            "collection": collection_name,
            "sa": self.sa_email,
            "enforced_filter_key": required_filter_key,
            "enforced_filters": filters if required_filter_key else None,
        }
