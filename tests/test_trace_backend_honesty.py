"""
tests/test_trace_backend_honesty.py — the trace backend may not be claimed
louder than it is (HOD-714, HOD-732).

WHAT WENT WRONG, IN ORDER. `HODI_TRACE_EXPORT=cloud` selected a Cloud Trace
exporter, and `opentelemetry-exporter-gcp-trace` was **not in
requirements.lock** — so the import failed, the code caught the exception, said
nothing, and fell back to the console exporter. For the entire life of that
setting the "durable trace backend" could ONLY ever have been the console. The
service started healthy, spans kept printing, and nothing anywhere indicated
that the observability claim was false.

Then, once the package was pinned and the exporter did build, spans still did
not arrive: `BatchSpanProcessor` flushes on a background thread, and Cloud Run
throttles CPU to approximately nothing between requests, so the flush never got
scheduled. Again: no error, no warning, no spans.

And when the spans finally did arrive, the id being reported was the wrong one.
The ADK runner starts its own root `invocation` span in its own execution
context, so the delegation is one coherent trace that an outer wrapper span does
not adopt — measured as 12 spans, 11 correlated under ADK's root and the wrapper
alone in a second trace. The endpoint had been handing back the wrapper's id,
which resolved in Cloud Trace to a single useless span.

Three failures, one shape: **every component reported success and the claim was
still false.** These tests assert the properties that make the claim checkable.
"""

import os
import re
import unittest
from pathlib import Path

from src.observability.tracing import active_exporter_kind

ROOT = Path(__file__).resolve().parent.parent
LOCKFILE = ROOT / "src" / "evidence_service" / "requirements.lock"
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"
TRACING = ROOT / "src" / "observability" / "tracing.py"


class TheExporterIsActuallyInstallableTest(unittest.TestCase):
    """A backend selected by an env var that no dependency can satisfy."""

    def test_the_cloud_exporter_is_pinned_in_the_lockfile(self):
        """
        Without this pin, HODI_TRACE_EXPORT=cloud is a no-op that looks like a
        feature. `make demo` installs from this lockfile and CI installs from
        this lockfile, so the pin is what makes the setting mean anything.
        """
        lock = LOCKFILE.read_text()
        self.assertIn("opentelemetry-exporter-gcp-trace==", lock,
                      "HODI_TRACE_EXPORT=cloud cannot work: the exporter is not pinned, so the "
                      "import fails and the service silently uses the console exporter.")

    def test_the_pin_is_an_exact_version(self):
        lock = LOCKFILE.read_text()
        m = re.search(r"opentelemetry-exporter-gcp-trace==([\d.]+)", lock)
        self.assertIsNotNone(m, "the exporter must be pinned to an exact version, like every other "
                                "model id and dependency in this project")


class TheFallbackIsNotSilentTest(unittest.TestCase):
    """A capability that degrades quietly is indistinguishable from one that works."""

    def test_a_failed_cloud_exporter_logs_at_error(self):
        src = TRACING.read_text()
        block = src[src.index("def _build_exporter"):src.index("def active_exporter_kind")]
        self.assertRegex(
            block, r"logging\.getLogger\([^)]*\)\.error",
            "the cloud->console fallback must log at ERROR. It was a bare `pass`, and that silence "
            "is why a broken durable backend looked healthy for days.")

    def test_the_fallback_names_what_to_check(self):
        src = TRACING.read_text()
        for hint in ("opentelemetry-exporter-gcp-trace", "cloudtrace.googleapis.com",
                     "roles/cloudtrace.agent"):
            self.assertIn(hint, src,
                          f"the fallback message should name '{hint}' — the operator has to be able "
                          "to act on it without reading this module")


class TheDeployDoesNotCreateTheSilentConditionTest(unittest.TestCase):
    """Do not set a flag whose preconditions are absent."""

    def test_deploy_checks_both_api_and_iam_before_enabling_cloud_export(self):
        sh = DEPLOY_SH.read_text()
        self.assertIn("HODI_TRACE_EXPORT=cloud", sh)
        # The guarded section: from the trace comment to the ASSIGNMENT that sets
        # the flag — not the comment above it that merely mentions the name.
        start = sh.index("# Durable trace backend")
        assign = sh.index('ENV_VARS="${ENV_VARS:+${ENV_VARS},}HODI_TRACE_EXPORT=cloud"', start)
        block = sh[start:assign]
        self.assertIn("cloudtrace.googleapis.com", block,
                      "deploy must verify the API is enabled before claiming Cloud Trace")
        self.assertIn("roles/cloudtrace.agent", block,
                      "deploy must verify the runtime identity can write traces before claiming it")


class TheReportedExporterMatchesRealityTest(unittest.TestCase):
    """`trace_exporter` in the API response is a claim like any other."""

    def setUp(self):
        self._prior = {k: os.environ.get(k) for k in ("HODI_TRACE_EXPORT", "HODI_OFFLINE")}

    def tearDown(self):
        for k, v in self._prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_offline_reports_console_regardless_of_the_request(self):
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ["HODI_OFFLINE"] = "1"
        self.assertEqual(active_exporter_kind(), "console",
                         "a declared-offline run must never report a durable backend")

    def test_unset_reports_console(self):
        os.environ.pop("HODI_TRACE_EXPORT", None)
        os.environ.pop("HODI_OFFLINE", None)
        self.assertEqual(active_exporter_kind(), "console")

    def test_a_requested_but_unavailable_backend_is_named_distinctly(self):
        """
        The dangerous case gets its OWN value rather than collapsing into
        "console": cloud was asked for and did not happen. Collapsing them is
        how the silent fallback stayed invisible.
        """
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ.pop("HODI_OFFLINE", None)
        kind = active_exporter_kind()
        self.assertIn(kind, ("cloud_trace", "console_fallback_after_cloud_requested"))
        if kind != "cloud_trace":
            self.assertNotEqual(kind, "console",
                                "a failed cloud export must not be reported as a plain console run")


class TheDelegationTraceIdIsTheDelegationsTest(unittest.TestCase):
    """The id returned must be the trace the agent spans are actually in."""

    def test_the_fleet_records_the_trace_id_from_inside_the_run(self):
        src = (ROOT / "src" / "fleet" / "adk_fleet.py").read_text()
        self.assertIn("_LAST_DELEGATION_TRACE", src)
        self.assertIn("delegation_trace_id", src,
                      "run_revocation_delegation must return the trace its spans went into")

    def test_the_route_returns_the_fleets_id_not_a_wrapper_span(self):
        """
        Pins the specific bug: the endpoint wrapped the call in its own span and
        returned THAT trace id, which Cloud Trace resolved to one useless span
        because the ADK runner had rooted the real delegation elsewhere.
        """
        src = (ROOT / "src" / "api" / "buyer_api.py").read_text()
        drill = src[src.index("async def fleet_delegation_drill"):]
        drill = drill[:drill.index("class CompromisedAgentRequest")]
        self.assertIn('result.get("delegation_trace_id")', drill,
                      "the drill must report the fleet's trace id, not one it minted itself")
        self.assertNotIn('start_as_current_span("hodi.revocation_delegation")', drill,
                         "the wrapper span created a second, empty trace — do not reintroduce it")

    def test_the_response_states_which_backend_it_used(self):
        src = (ROOT / "src" / "api" / "buyer_api.py").read_text()
        drill = src[src.index("async def fleet_delegation_drill"):]
        drill = drill[:drill.index("class CompromisedAgentRequest")]
        self.assertIn('"trace_exporter"', drill,
                      "a trace_id with no exporter named lets a console run read as a durable one")


if __name__ == "__main__":
    unittest.main()
