import unittest
import time
import os
import signal
import sys
from src.supervisor.supervisor import Supervisor
from src.supervisor.quarantine import QuarantineEngine
from src.registry.registry import AgentRegistry, AgentPublication

class TestSupervisor(unittest.TestCase):
    """
    Supervisor Tests: HOD-341 (Detection & Bounding via Deadline-Driven & Process-Exit Paths) & HOD-342 (Quarantine & Reroute).
    """

    def setUp(self):
        self.supervisor = Supervisor(deadline_seconds=0.3, failure_threshold=2)
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

    def test_hod341_path_a_deadline_driven_detection_without_cooperation(self):
        """
        HOD-341 Path A (STRONG DEADLINE-DRIVEN DETECTION):
        Subprocess sleeps longer than deadline (or is killed silently).
        The supervisor observes ONLY that no result arrived before deadline_seconds,
        and asserts TaskAbandoned(reason='deadline_exceeded', written_by='supervisor') is written.
        Zero exit-code cooperation or status event from the killed worker process.
        """
        # Subprocess sleeps for 10 seconds (exceeding 0.3s supervisor deadline)
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

        with self.assertRaises(TimeoutError):
            self.supervisor.execute_bounded_subprocess("worker-agent-failing", cmd)

        # Assert TaskAbandoned was written strictly BY THE SUPERVISOR with reason 'deadline_exceeded'
        self.assertEqual(len(self.supervisor.abandoned_events), 1)
        event = self.supervisor.abandoned_events[0]
        self.assertEqual(event.agent_id, "worker-agent-failing")
        self.assertEqual(event.written_by, "supervisor", "TaskAbandoned MUST be written BY THE SUPERVISOR!")
        self.assertEqual(event.reason, "deadline_exceeded", "Reason MUST be 'deadline_exceeded' on deadline path!")

    def test_hod341_path_b_process_exit_fast_path(self):
        """
        HOD-341 Path B (PROCESS-EXIT FAST PATH):
        Subprocess is SIGKILL'd mid-execution, exiting with non-zero exit code.
        Supervisor catches fast exit and writes TaskAbandoned (written_by='supervisor').
        """
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

        with self.assertRaises(RuntimeError):
            self.supervisor.execute_bounded_subprocess("worker-agent-failing", cmd, kill_sig=signal.SIGKILL)

        self.assertEqual(len(self.supervisor.abandoned_events), 1)
        event = self.supervisor.abandoned_events[0]
        self.assertEqual(event.agent_id, "worker-agent-failing")
        self.assertEqual(event.written_by, "supervisor")
        self.assertIn("process_exit_error", event.reason)

    def test_hod342_quarantine_and_reroute_completes_request(self):
        """
        HOD-342 Test:
        Failing worker is quarantined, deregistered from Registry, task rerouted to standby,
        and request completes successfully.
        """
        self.assertIn("worker-agent-failing", self.registry._publications)

        def standby_fallback_func():
            return {"status": "SUCCESS", "terms": "standard_license_terms"}

        result = self.quarantine_engine.quarantine_and_reroute(
            quarantined_agent_id="worker-agent-failing",
            standby_agent_id="standby-agent-002",
            fallback_func=standby_fallback_func
        )

        self.assertNotIn("worker-agent-failing", self.registry._publications)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["terms"], "standard_license_terms")
        self.assertEqual(result["quarantine_notice"]["request_status"], "completed_via_reroute")

if __name__ == "__main__":
    unittest.main()
