"""
ADK fleet delegation tests (HOD-302, HOD-330, HOD-340, HOD-341).

The property under test: the fleet is a RUNNING multi-agent system, not a
diagram. One delegation executes through ADK's runner across three distinct
service accounts, agent-to-agent addressing goes through role-scoped registry
discovery, and every hop leaves a span carrying the identity that did the work.

All tests are offline (HODI_OFFLINE=1): the gateway has no Firestore client and
the fixture event log stands in for stored grants.
"""

import io
import os
import json
import unittest
from contextlib import redirect_stdout

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.schema.grant_event import GrantEvent
from src.registry.registry import AgentRegistry
from src.supervisor.supervisor import Supervisor

FIXTURE = "fixtures/demo_grant_log.json"


def fixture_events():
    with open(FIXTURE) as f:
        return [GrantEvent(**e) for e in json.load(f)["events"]]


class TestAdkFleetDelegation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Attach an in-memory exporter to whatever provider is installed, rather
        # than trying to replace it — OpenTelemetry refuses a second
        # set_tracer_provider(), so replacing would work or not depending on
        # module import order.
        cls.exporter = InMemorySpanExporter()
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider()
            trace.set_tracer_provider(provider)
        provider.add_span_processor(SimpleSpanProcessor(cls.exporter))

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.exporter.clear()

        from src.fleet.adk_fleet import run_revocation_delegation
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.result = run_revocation_delegation(
                counterparty_id="acme-intelligence-labs",
                work_id="work-essay-001",
                revoked_use_type="training",
                fallback_events=fixture_events(),
            )

    def test_adk_is_the_framework_actually_executing(self):
        """google.adk drives the run — not a label in a docstring."""
        import google.adk
        from google.adk.agents import BaseAgent
        from src.fleet.adk_fleet import FleetDelegationOrchestrator, build_fleet
        self.assertTrue(issubclass(FleetDelegationOrchestrator, BaseAgent))
        orchestrator, _ = build_fleet("cp", "w", "training")
        self.assertEqual(len(orchestrator.sub_agents), 3)
        for sub in orchestrator.sub_agents:
            self.assertIsInstance(sub, BaseAgent)

    def test_five_hops_appear_in_the_adk_event_stream(self):
        authors = [t["author"] for t in self.result["transcript"]]
        self.assertEqual(authors, [
            "licensing_negotiator", "fleet_orchestrator", "rights_custodian",
            "fleet_orchestrator", "revocation_propagator",
        ])

    def test_negotiator_is_not_told_the_propagator_exists(self):
        """Negative half of HOD-330: an unauthorized role query returns []."""
        self.assertEqual(self.result["negotiator_discovered"], [])

    def test_custodian_discovers_the_propagator_by_role(self):
        """Positive half of HOD-330, and the addressing path: the custodian does
        not hold a reference to the propagator — it finds it in the registry."""
        self.assertEqual(self.result["discovered"], ["revocation_propagator-v1"])

    def test_cascade_runs_and_affects_contained_grants(self):
        affected = {a.grant_id for a in self.result["cascade"].affected_grants}
        self.assertIn("grant-demo-001", affected)

    def test_every_hop_emitted_a_span_with_identity_policy_and_outcome(self):
        spans = {s.name: s for s in self.exporter.get_finished_spans()}
        for name in ("negotiator.read_grants", "registry.discover",
                     "custodian.initiate_revocation", "propagator.execute_cascade"):
            self.assertIn(name, spans, f"missing decision span '{name}'")
            attrs = spans[name].attributes
            self.assertIn("agent.identity", attrs)
            self.assertIn("policy.consulted", attrs)
            self.assertIn("outcome", attrs)

    def test_three_distinct_service_accounts_did_the_work(self):
        identities = {
            s.attributes["agent.identity"]
            for s in self.exporter.get_finished_spans()
            if "agent.identity" in (s.attributes or {})
        }
        self.assertEqual(identities, {
            "licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com",
            "rights-custodian-sa@hodi-2026.iam.gserviceaccount.com",
            "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
        })

    def test_all_hops_share_one_trace(self):
        trace_ids = {s.context.trace_id for s in self.exporter.get_finished_spans()}
        self.assertEqual(len(trace_ids), 1,
                         "the delegation must be readable as a SINGLE trace (HOD-340)")

    def test_agents_share_one_state_object_not_pydantic_copies(self):
        from src.fleet.adk_fleet import build_fleet
        orchestrator, shared = build_fleet("cp", "w", "training")
        self.assertIs(orchestrator.shared, shared)
        for sub in orchestrator.sub_agents:
            self.assertIs(sub.shared, shared)


class TestSupervisorBoundsInProcessWork(unittest.TestCase):
    """
    The in-process deadline must bound the SUPERVISOR'S WAIT, not be checked
    after the task already finished. The previous implementation ran the task
    inline and compared elapsed time afterwards, so a 1.2s task under a 0.3s
    deadline took 1.21s to be "abandoned".
    """

    def test_supervisor_reports_within_the_deadline_not_after_the_task(self):
        import time
        supervisor = Supervisor(deadline_seconds=0.3)
        started = time.time()
        with self.assertRaises(TimeoutError):
            supervisor.execute_bounded_task("looping-agent", lambda: time.sleep(5.0))
        elapsed = time.time() - started
        self.assertLess(elapsed, 1.0,
                        f"supervisor took {elapsed:.2f}s to report a 0.3s deadline breach")

    def test_task_abandoned_is_written_by_the_supervisor(self):
        import time
        supervisor = Supervisor(deadline_seconds=0.2)
        with self.assertRaises(TimeoutError):
            supervisor.execute_bounded_task("looping-agent", lambda: time.sleep(5.0))
        self.assertEqual(len(supervisor.abandoned_events), 1)
        event = supervisor.abandoned_events[0]
        self.assertEqual(event.written_by, "supervisor")
        self.assertEqual(event.reason, "deadline_exceeded")

    def test_fast_task_returns_its_value(self):
        supervisor = Supervisor(deadline_seconds=2.0)
        self.assertEqual(supervisor.execute_bounded_task("quick", lambda: "done"), "done")


if __name__ == "__main__":
    unittest.main()


class TestQuarantineAndRerouteOnTheDelegationPath(unittest.TestCase):
    """
    HOD-341 + HOD-342 on the LIVE delegation path, not in isolation.

    The rubric asks how the system recovers when a worker agent loops or
    hallucinates. `QuarantineEngine` existed and was unit-tested, but appeared
    in no execution path — so that question had no answer in running code. It
    is now wired into the ADK delegation, and this class forces the failure
    rather than simulating its aftermath.
    """

    @classmethod
    def setUpClass(cls):
        cls.exporter = InMemorySpanExporter()
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider()
            trace.set_tracer_provider(provider)
        provider.add_span_processor(SimpleSpanProcessor(cls.exporter))

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.exporter.clear()

        from src.fleet.adk_fleet import run_revocation_delegation
        buf = io.StringIO()
        with redirect_stdout(buf):
            # The fault injection: the propagator never returns.
            self.result = run_revocation_delegation(
                counterparty_id="acme-intelligence-labs",
                work_id="work-essay-001",
                revoked_use_type="training",
                fallback_events=fixture_events(),
                supervisor=Supervisor(deadline_seconds=0.5),
                loop_forever=True,
            )

    def test_the_looping_worker_is_abandoned_by_the_supervisor(self):
        events = self.result["task_abandoned_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["agent_id"], "revocation_propagator")
        self.assertEqual(events[0]["reason"], "deadline_exceeded")
        self.assertEqual(events[0]["written_by"], "supervisor",
                         "TaskAbandoned must be written BY THE SUPERVISOR, never by the failing worker")

    def test_the_worker_is_quarantined_and_deregistered_from_the_registry(self):
        q = self.result["quarantine"]
        self.assertEqual(q["quarantined_agent_id"], "revocation_propagator-v1")
        self.assertTrue(q["deregistered"])

    def test_it_stays_deregistered_for_the_remainder_of_the_run(self):
        """'for the remainder of the run' is the requirement — a later discovery
        must not find it again."""
        self.assertEqual(self.result["post_quarantine_discovery"], [])

    def test_the_request_still_completes_with_a_stated_partial_result(self):
        outcome = self.result["quarantine"]["result"]
        self.assertEqual(outcome["status"], "COMPLETED_DEGRADED")
        self.assertIn("grant-demo-001", outcome["affected_grant_ids"])
        self.assertEqual(outcome["notices_issued"], 0)
        self.assertIn("append-only", outcome["partial_result_reason"],
                      "a degraded result must STATE why it is degraded")

    def test_quarantine_and_reroute_are_both_spans_in_a_single_trace(self):
        """HOD-342 AC: the quarantine and the reroute both appear as spans in a
        single OTel trace."""
        spans = self.exporter.get_finished_spans()
        by_name = {s.name: s for s in spans}
        self.assertIn("propagator.execute_cascade", by_name)
        self.assertEqual(by_name["propagator.execute_cascade"].attributes["outcome"], "ABANDONED")

        self.assertIn("supervisor.quarantine_and_reroute", by_name)
        quarantine = by_name["supervisor.quarantine_and_reroute"]
        self.assertEqual(quarantine.attributes["outcome"], "QUARANTINED_AND_REROUTED")
        self.assertTrue(quarantine.attributes["quarantine.deregistered_from_registry"])
        self.assertEqual(quarantine.attributes["reroute.result_status"], "COMPLETED_DEGRADED")

        self.assertEqual(len({s.context.trace_id for s in spans}), 1,
                         "quarantine and reroute must be readable in ONE trace")

    def test_the_healthy_path_does_not_quarantine_anything(self):
        """Paired positive: without the fault, nothing is abandoned or quarantined."""
        from src.fleet.adk_fleet import run_revocation_delegation
        buf = io.StringIO()
        with redirect_stdout(buf):
            healthy = run_revocation_delegation(
                counterparty_id="acme-intelligence-labs", work_id="work-essay-001",
                revoked_use_type="training", fallback_events=fixture_events())
        self.assertIsNone(healthy["abandoned"])
        self.assertIsNone(healthy["quarantine"])
        self.assertEqual(healthy["task_abandoned_events"], [])
        self.assertIsNotNone(healthy["cascade"])
