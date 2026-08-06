from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from src.schema.iam_policy import is_action_permitted, AGENT_SA_MAP

class AgentPublication(BaseModel):
    agent_id: str
    name: str
    version: str
    owning_function: str  # rights_custodian, licensing_negotiator, evidence_agent, revocation_propagator
    role: str
    scopes: List[str]

class AgentRegistry:
    """
    Agent Registry (HOD-330).
    Agents published with version, scope, and owning function.
    
    Correction 5(b): discover(role, requesting_sa) returns EMPTY RESULT ([]) if requesting_sa
    is unauthorized to invoke the target agent role. Does NOT throw error or leak existence.
    """

    def __init__(self):
        self._publications: Dict[str, AgentPublication] = {}
        # Matrix of authorized inter-agent invocations
        self._allowed_invocations: Dict[str, List[str]] = {
            "rights_custodian": ["rights_custodian"],
            "licensing_negotiator": ["licensing_negotiator", "rights_custodian"],
            "evidence_agent": ["evidence_agent"],
            "revocation_propagator": ["revocation_propagator", "evidence_agent"],
            "supervisor": ["rights_custodian", "licensing_negotiator", "evidence_agent", "revocation_propagator"]
        }

    def register(self, publication: AgentPublication):
        self._publications[publication.agent_id] = publication

    def discover(self, target_role: str, requesting_role_key: str) -> List[AgentPublication]:
        """
        Returns agents matching target_role IF requesting_role_key is authorized.
        Correction 5(b): If unauthorized, returns [] (EMPTY RESULT) to avoid disclosing agent existence.
        """
        allowed_targets = self._allowed_invocations.get(requesting_role_key, [])
        if target_role not in allowed_targets:
            # Silent non-disclosure: return empty list
            return []

        return [pub for pub in self._publications.values() if pub.owning_function == target_role or pub.role == target_role]
