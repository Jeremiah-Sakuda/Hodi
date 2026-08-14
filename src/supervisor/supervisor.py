import time
import threading
import subprocess
import signal
import os
import uuid
from typing import Dict, Any, Callable, Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone

from src.supervisor.lease import LeaseLedger

def _accepts_lease_kwarg(func: Callable[..., Any]) -> bool:
    """True if `func` can take a lease_id keyword (explicitly or via **kwargs)."""
    import inspect
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if "lease_id" in sig.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


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

    With a LeaseLedger attached (HOD-707), the Supervisor also fences the
    worker's WRITES: a lease is issued before dispatch and revoked at the
    moment of abandonment — before quarantine, before reroute — so a worker
    that wakes up after its deadline can still compute but can no longer
    commit. Revocation is ordered BEFORE the TimeoutError is raised: the
    instant the fleet learns the task is abandoned, the ledger already
    refuses the lease.
    """

    def __init__(self, deadline_seconds: float = 5.0, failure_threshold: int = 3,
                 lease_ledger: Optional[LeaseLedger] = None,
                 lease_grace_seconds: float = 30.0):
        self.deadline_seconds = deadline_seconds
        self.failure_threshold = failure_threshold
        self.failure_counts: Dict[str, int] = {}
        self.circuit_breakers: Dict[str, bool] = {}  # True = tripped
        self.abandoned_events: List[TaskAbandonedEvent] = []
        self.lease_ledger = lease_ledger
        # Lease TTL = deadline + grace. The TTL is the backstop for a DEAD
        # supervisor (its revoke never ran); the live supervisor's explicit
        # revoke is the primary mechanism and fires at the deadline itself.
        self.lease_grace_seconds = lease_grace_seconds

    def execute_bounded_task(self, agent_id: str, task_func: Callable[..., Any],
                             task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes agent task with wall-clock deadline and circuit breaker.
        If deadline is exceeded or circuit breaker is tripped, SUPERVISOR writes TaskAbandoned event.

        With a lease ledger attached, `task_func` is called with a `lease_id`
        keyword argument when it accepts one; the worker must present that
        lease on every side-effecting write (the gateway checks it — the
        worker's cooperation is not part of the guarantee).
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

        lease_id: Optional[str] = None
        if self.lease_ledger is not None:
            lease_id = self.lease_ledger.issue(
                agent_id=agent_id,
                task_id=task_id or f"task-{uuid.uuid4()}",
                ttl_seconds=self.deadline_seconds + self.lease_grace_seconds,
            )

        # The task runs on a separate thread and the SUPERVISOR waits with a
        # timeout, so the deadline bounds the supervisor's wait rather than
        # being checked after the fact. An earlier version called task_func()
        # inline and compared elapsed time afterwards — under that version a
        # 1.2s task with a 0.3s deadline took 1.21s to be "abandoned", so the
        # deadline bounded nothing at all in-process.
        #
        # A Python thread cannot be forcibly killed; the property being proven
        # is that the supervisor DETECTS and reports within the deadline without
        # the worker's cooperation — and, with a ledger attached, that the
        # worker's LEASE dies with the deadline, so late writes are refused at
        # the gateway. The orphaned worker is a daemon thread and cannot keep
        # the process alive. For hard termination of an uncooperative worker,
        # use execute_bounded_subprocess (Path A).
        result_box: Dict[str, Any] = {}

        def _runner():
            try:
                if lease_id is not None and _accepts_lease_kwarg(task_func):
                    result_box["value"] = task_func(lease_id=lease_id)
                else:
                    result_box["value"] = task_func()
            except BaseException as exc:  # noqa: BLE001 — reported on the caller's thread
                result_box["error"] = exc

        worker = threading.Thread(target=_runner, name=f"hodi-agent-{agent_id}", daemon=True)
        start_time = time.time()
        worker.start()
        worker.join(timeout=self.deadline_seconds)

        if worker.is_alive():
            # DEADLINE PATH: no result arrived in time. Revoke the lease FIRST
            # — from this instant the worker can compute but cannot commit —
            # then write TaskAbandoned. The supervisor writes it itself; the
            # worker is still running and has reported nothing.
            if self.lease_ledger is not None and lease_id is not None:
                self.lease_ledger.revoke(lease_id, reason=f"deadline_exceeded ({self.deadline_seconds}s) for agent '{agent_id}'")
            self._handle_failure(agent_id, "deadline_exceeded")
            raise TimeoutError(
                f"SUPERVISOR_BOUND: No result within deadline {self.deadline_seconds}s "
                f"(supervisor waited {time.time() - start_time:.2f}s). "
                "TaskAbandoned written by supervisor."
            )

        if "error" in result_box:
            if self.lease_ledger is not None and lease_id is not None:
                self.lease_ledger.revoke(lease_id, reason=f"worker_error for agent '{agent_id}'")
            self._handle_failure(agent_id, f"error: {result_box['error']}")
            raise result_box["error"]

        # Reset failure count on success; the finished task's lease is released
        # so it cannot be replayed by anything holding the id.
        if self.lease_ledger is not None and lease_id is not None:
            self.lease_ledger.release(lease_id)
        self.failure_counts[agent_id] = 0
        return result_box.get("value")

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
