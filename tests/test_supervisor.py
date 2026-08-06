import unittest
import time
from src.supervisor.supervisor import Supervisor
from src.supervisor.quarantine import QuarantineEngine
from src.registry.registry import AgentRegistry, AgentPublication

class TestSupervisor(unittest.TestCase):
    """
    Supervisor Tests: HOD-341 (Detection & Bounding) & HOD-342 (Quarantine & Reroute).
    """

    def setUp(self):
        self.supervisor = Supervisor(deadline_seconds=0.1, failure_threshold=2)
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

    def test_hod341_task_abandoned_written_by_supervisor_on_timeout(self):
        """
        HOD-341 Test:
        Hard-kill / timeout mid-call results in TaskAbandoned event written BY THE SUPERVISOR,
        never by the failing worker process.
        """
        def slow_worker_func():
            time.sleep(0.3)
            return {"result": "ok"}

        with self.assertRaises(TimeoutError):
            self.supervisor.execute_bounded_task("worker-agent-failing", slow_worker_func)

        self.assertEqual(len(self.supervisor.abandoned_events), 1)
        event = self.supervisor.abandoned_events[0]
        self.assertEqual(event.agent_id, "worker-agent-failing")
        self.assertEqual(event.written_by, "supervisor", "TaskAbandoned MUST be written BY THE SUPERVISOR!")
        self.assertEqual(event.reason, "deadline_exceeded")

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
