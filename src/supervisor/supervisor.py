import time
import subprocess
import signal
import os
from typing import Dict, Any, Callable, Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone

class TaskAbandonedEvent(BaseModel):
    event_id: str
    agent_id: str
    written_by: str = "supervisor"  # MUST be written BY THE SUPERVISOR (HOD-341)
    reason: str  # "deadline_exceeded" | "circuit_breaker_tripped" | "process_exit_error"
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
        self.abandoned_events: List[TaskAbandonedEvent] = []

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

    def execute_bounded_subprocess(self, agent_id: str, cmd: List[str], kill_sig: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes child subprocess under strict Supervisor deadline.
        Path A (Deadline-Driven Detection): If process does not complete before deadline_seconds,
        Supervisor marks task abandoned (reason: 'deadline_exceeded', written_by: 'supervisor') WITHOUT OS exit-code cooperation.
        Path B (Process-Exit Fast Path): If process exits prematurely with non-zero code, supervisor writes TaskAbandoned (reason: 'process_exit_error').
        """
        proc = subprocess.Popen(cmd)
        
        if kill_sig is not None:
            # Simulate uncooperative external SIGKILL mid-execution
            time.sleep(0.05)
            try:
                os.kill(proc.pid, kill_sig)
            except ProcessLookupError:
                pass

        try:
            # SUPERVISOR OBSERVES ONLY WHETHER A RESULT ARRIVES BEFORE DEADLINE
            stdout, stderr = proc.communicate(timeout=self.deadline_seconds)
            if proc.returncode != 0:
                self._handle_failure(agent_id, f"process_exit_error_code_{proc.returncode}")
                raise RuntimeError(f"SUPERVISOR_BOUND: Subprocess exited with non-zero code {proc.returncode}. TaskAbandoned written by supervisor.")
            return {"status": "ok", "stdout": stdout}

        except subprocess.TimeoutExpired:
            # DEADLINE PATH: NO RESULT ARRIVED BEFORE DEADLINE!
            # Supervisor forces cleanup and writes TaskAbandoned with reason="deadline_exceeded"
            proc.kill()
            proc.wait()
            self._handle_failure(agent_id, "deadline_exceeded")
            raise TimeoutError(f"SUPERVISOR_BOUND: Deadline {self.deadline_seconds}s exceeded with no result. TaskAbandoned written by supervisor.")

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
