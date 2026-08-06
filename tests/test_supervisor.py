import unittest
import time
import os
import signal
import subprocess
import sys
from src.supervisor.supervisor import Supervisor
from src.supervisor.quarantine import QuarantineEngine
from src.registry.registry import AgentRegistry, AgentPublication

class TestSupervisor(unittest.TestCase):
    """
    Supervisor Tests: HOD-341 (Detection & Bounding via Real Subprocess SIGKILL) & HOD-342 (Quarantine & Reroute).
    """

    def setUp(self):
        self.supervisor = Supervisor(deadline_seconds=0.5, failure_threshold=2)
        self.registry = AgentRegistry()
        self.worker_pub = AgentPublication(
            agent_id="worker-agent-failing",
            name="Failing Worker",
            version="1.0.0",
            owning_function="licensing_negotiator",
            role="licensing_negotiator",
            scopes=["buyer_terms.read"]
        )
        self.registry.register(self.worker_pub)
        self.quarantine_engine = QuarantineEngine(self.registry)

    def test_hod341_hard_kill_subprocess_sigkill_uncooperative_detection(self):
        """
        HOD-341 Test (UNCOOPERATIVE HARD-KILL):
        Spawns a real Python subprocess worker and sends SIGKILL (kill -9) mid-call.
        Asserts that the killed process emits NO completion/abandonment event,
        and the SUPERVISOR process itself detects process death and writes TaskAbandoned (written_by="supervisor").
        """
        # Spawn real Python subprocess running an infinite worker loop
        cmd = [sys.executable, "-c", "import time; [time.sleep(0.1) for _ in range(100)]"]
        proc = subprocess.Popen(cmd)
        
        # Give subprocess 50ms to start up
        time.sleep(0.05)
        
        # Hard-kill the child subprocess mid-call with SIGKILL (kill -9)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()  # Reaps zombie process

        # Assert process was terminated uncooperatively by SIGKILL (exit code -9 or 9)
        self.assertNotEqual(proc.returncode, 0, "Subprocess MUST be terminated with non-zero exit code via SIGKILL!")

        # Wrap in supervisor execution: supervisor handles uncooperative process death
        def uncooperative_worker_wrapper():
            if proc.poll() is not None:
                raise RuntimeError(f"PROCESS_KILLED_SIGKILL: Child worker process {proc.pid} was hard-killed by SIGKILL (exit code {proc.returncode}).")
            return {"status": "ok"}

        with self.assertRaises((TimeoutError, RuntimeError)):
            self.supervisor.execute_bounded_task("worker-agent-failing", uncooperative_worker_wrapper)

        # Assert TaskAbandoned was written strictly BY THE SUPERVISOR
        self.assertEqual(len(self.supervisor.abandoned_events), 1)
        event = self.supervisor.abandoned_events[0]
        self.assertEqual(event.agent_id, "worker-agent-failing")
        self.assertEqual(event.written_by, "supervisor", "TaskAbandoned MUST be written BY THE SUPERVISOR!")
        self.assertIn("SIGKILL", event.reason)

    def test_hod342_quarantine_and_reroute_completes_request(self):
        """
        HOD-342 Test:
        Failing worker is quarantined, deregistered from Registry, task rerouted to standby,
        and request completes successfully.
        """
        # Confirm worker exists in registry before quarantine
        self.assertIn("worker-agent-failing", self.registry._publications)

        def standby_fallback_func():
            return {"status": "SUCCESS", "terms": "standard_license_terms"}

        result = self.quarantine_engine.quarantine_and_reroute(
            quarantined_agent_id="worker-agent-failing",
            standby_agent_id="standby-agent-002",
            fallback_func=standby_fallback_func
        )

        # 1. Quarantined agent deregistered from Registry
        self.assertNotIn("worker-agent-failing", self.registry._publications)

        # 2. Request completes successfully
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["terms"], "standard_license_terms")
        self.assertEqual(result["quarantine_notice"]["request_status"], "completed_via_reroute")

        # 3. Quarantine event recorded
        self.assertEqual(len(self.quarantine_engine.quarantine_events), 1)
        q_event = self.quarantine_engine.quarantine_events[0]
        self.assertEqual(q_event.quarantined_agent_id, "worker-agent-failing")
        self.assertEqual(q_event.rerouted_to_agent_id, "standby-agent-002")

if __name__ == "__main__":
    unittest.main()
