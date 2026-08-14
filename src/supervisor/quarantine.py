from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from src.registry.registry import AgentRegistry

class QuarantineEvent(BaseModel):
    event_id: str
    quarantined_agent_id: str
    rerouted_to_agent_id: str
    timestamp: datetime
    status: str = "quarantined_and_rerouted"

class QuarantineEngine:
    """
    Supervisor — Quarantine and Reroute (HOD-342).
    Deregisters looping/quarantined worker from Registry for remainder of run.
    Reroutes task to standby instance or degrades to partial result; request completes.
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.quarantine_events: List[QuarantineEvent] = []

    def quarantine_and_reroute(
        self,
        quarantined_agent_id: str,
        standby_agent_id: str,
        fallback_func: Any
    ) -> Dict[str, Any]:
        """
        Quarantines failing worker, deregisters from registry, reroutes task to standby agent,
        and returns complete response.
        """
        # 1. Deregister the quarantined agent from the registry — an appended
        # EVENT with a reason (HOD-709), never a deletion: the publication
        # history survives quarantine, and discovery simply stops disclosing
        # the agent for the remainder of the run.
        if self.registry.is_registered(quarantined_agent_id):
            self.registry.deregister(quarantined_agent_id, reason="quarantined_by_supervisor")

        # 2. Record QuarantineEvent
        event = QuarantineEvent(
            event_id=f"quarantine-{len(self.quarantine_events)+1}",
            quarantined_agent_id=quarantined_agent_id,
            rerouted_to_agent_id=standby_agent_id,
            timestamp=datetime.now(timezone.utc)
        )
        self.quarantine_events.append(event)

        # 3. Reroute task to standby agent or fallback function
        result = fallback_func()
        result["quarantine_notice"] = {
            "quarantined_agent_id": quarantined_agent_id,
            "rerouted_to_agent_id": standby_agent_id,
            "request_status": "completed_via_reroute"
        }

        return result
