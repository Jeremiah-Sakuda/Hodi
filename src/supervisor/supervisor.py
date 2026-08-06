import time
from typing import Dict, Any, Callable, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

class TaskAbandonedEvent(BaseModel):
    event_id: str
    agent_id: str
    written_by: str = "supervisor"  # MUST be written BY THE SUPERVISOR (HOD-341)
    reason: str  # "deadline_exceeded" | "circuit_breaker_tripped"
    timestamp: datetime

class Supervisor:
    """
    Supervisor — Detection and Bounding (HOD-341).
    Per-agent wall-clock deadline & circuit breaker.
    TaskAbandoned event is written BY THE SUPERVISOR, never by the failing worker process.
    """

    def __init__(self, deadline_seconds: float = 5.0, failure_threshold: int = 3):
        self.deadline_seconds = deadline_seconds
        self.failure_threshold = failure_threshold
        self.failure_counts: Dict[str, int] = {}
        self.circuit_breakers: Dict[str, bool] = {}  # True = tripped
        self.abandoned_events: list = []

    def execute_bounded_task(self, agent_id: str, task_func: Callable[[], Any]) -> Dict[str, Any]:
        """
        Executes agent task with wall-clock deadline and circuit breaker.
        If deadline is exceeded or circuit breaker is tripped, SUPERVISOR writes TaskAbandoned event.
        """
        if self.circuit_breakers.get(agent_id, False):
            # Circuit breaker already tripped! Supervisor writes TaskAbandoned event
            event = TaskAbandonedEvent(
                event_id=f"abandoned-{len(self.abandoned_events)+1}",
                agent_id=agent_id,
                written_by="supervisor",
                reason="circuit_breaker_tripped",
                timestamp=datetime.now(timezone.utc)
            )
            self.abandoned_events.append(event)
            raise TimeoutError(f"SUPERVISOR_BOUND: Circuit breaker tripped for agent '{agent_id}'. TaskAbandoned written by supervisor.")

        start_time = time.time()
        try:
            res = task_func()
            elapsed = time.time() - start_time
            if elapsed > self.deadline_seconds:
                self._handle_failure(agent_id, "deadline_exceeded")
                raise TimeoutError(f"SUPERVISOR_BOUND: Task execution time {elapsed:.2f}s exceeded deadline {self.deadline_seconds}s. TaskAbandoned written by supervisor.")
            
            # Reset failure count on success
            self.failure_counts[agent_id] = 0
            return res

        except Exception as e:
            if isinstance(e, TimeoutError):
                raise
            self._handle_failure(agent_id, f"error: {str(e)}")
            raise

    def _handle_failure(self, agent_id: str, reason: str):
        count = self.failure_counts.get(agent_id, 0) + 1
        self.failure_counts[agent_id] = count

        if count >= self.failure_threshold:
            self.circuit_breakers[agent_id] = True

        event = TaskAbandonedEvent(
            event_id=f"abandoned-{len(self.abandoned_events)+1}",
            agent_id=agent_id,
            written_by="supervisor",
            reason=reason,
            timestamp=datetime.now(timezone.utc)
        )
        self.abandoned_events.append(event)
