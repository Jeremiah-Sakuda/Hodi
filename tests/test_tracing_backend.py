"""
Durable trace export selection (HOD-714).

The property under test: the exporter is chosen by environment, the offline
default stays the console exporter (so `make demo` and the suite remain
credential-free), and an unavailable Cloud backend degrades to console
rather than breaking instrumentation. The span ATTRIBUTES are unchanged
either way — only the destination moves.
"""

import builtins
import os
import unittest
from unittest import mock

from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from src.observability import tracing


class TestExporterSelection(unittest.TestCase):
    def _clear(self):
        for k in ("HODI_TRACE_EXPORT", "HODI_OFFLINE"):
            os.environ.pop(k, None)

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("HODI_TRACE_EXPORT", "HODI_OFFLINE")}
        self.addCleanup(self._restore)
        self._clear()

    def _restore(self):
        self._clear()
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_default_is_console(self):
        proc = tracing._build_exporter()
        self.assertIsInstance(proc, BatchSpanProcessor)
        self.assertIsInstance(proc.span_exporter, ConsoleSpanExporter)

    def test_offline_forces_console_even_if_cloud_requested(self):
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ["HODI_OFFLINE"] = "1"
        proc = tracing._build_exporter()
        self.assertIsInstance(proc.span_exporter, ConsoleSpanExporter)

    def test_cloud_requested_but_unimportable_degrades_to_console(self):
        """
        An unavailable exporter must fall back, never crash — losing spans is
        worse than exporting them to the console.

        THE FAILURE THIS ASSERTION IS RECOVERING FROM. This test used to prove
        the fallback by relying on `opentelemetry-exporter-gcp-trace` genuinely
        being absent, and its docstring said so: "the Cloud Trace exporter is
        not a pinned dependency in the offline image". That was true, and it was
        the bug — `HODI_TRACE_EXPORT=cloud` could not select anything, so the
        durable trace backend could only ever have been the console. The test
        was therefore asserting the defect as the expected behaviour, and it
        went green for exactly as long as the capability was broken. Pinning the
        dependency turned it red, in CI, on the very run that proved the backend
        works.

        So the fallback is now forced by making the IMPORT fail, which tests the
        property on any machine and does not quietly depend on a missing
        package. `test_cloud_is_selected_when_the_exporter_is_available` asserts
        the other half, so neither direction can rot alone.
        """
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ.pop("HODI_OFFLINE", None)
        real_import = builtins.__import__

        def refuse_the_exporter(name, *a, **k):
            if "cloud_trace" in name:
                raise ImportError("forced: exporter unavailable")
            return real_import(name, *a, **k)

        with mock.patch.object(builtins, "__import__", refuse_the_exporter):
            proc = tracing._build_exporter()
        self.assertIsInstance(proc.span_exporter, ConsoleSpanExporter)

    def test_the_failed_fallback_is_reported_at_error(self):
        """A silent degrade is what made the broken backend invisible."""
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ.pop("HODI_OFFLINE", None)
        real_import = builtins.__import__

        def refuse_the_exporter(name, *a, **k):
            if "cloud_trace" in name:
                raise ImportError("forced: exporter unavailable")
            return real_import(name, *a, **k)

        with mock.patch.object(builtins, "__import__", refuse_the_exporter):
            with self.assertLogs("hodi.observability", level="ERROR") as caught:
                tracing._build_exporter()
        self.assertTrue(any("DURABLE" in m or "durable" in m for m in caught.output),
                        "the fallback must say that nothing is being written durably")

    def test_cloud_is_selected_when_the_exporter_is_available(self):
        """
        The half that was never asserted. Without it, removing the dependency
        again would pass every test in this file.
        """
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        except Exception:
            self.skipTest("exporter not importable in this environment")
        # BOTH halves are preconditions, and the second was learned the hard
        # way: with the package installed but no application-default
        # credentials, CloudTraceSpanExporter(...) raises while building its
        # client and the code falls back to the console. That is correct
        # behaviour, so asserting "installed => cloud" is too strong. The real
        # property is "installed AND authenticated => cloud", which is exactly
        # the condition on the deployed service and in the credentialed CI job.
        try:
            import google.auth
            google.auth.default()
        except Exception:
            self.skipTest("no application-default credentials; the fallback here is correct")
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ.pop("HODI_OFFLINE", None)
        proc = tracing._build_exporter()
        self.assertIsInstance(proc.span_exporter, CloudTraceSpanExporter,
                              "the exporter is installed and cloud was requested, so cloud must be "
                              "selected — a console exporter here means the durable backend is a "
                              "no-op again")

    def test_span_attributes_are_exporter_independent(self):
        span = tracing.create_agent_decision_span(
            "t.decision", "agent-x", "policy-y", "OUTCOME_Z")
        # Attributes are set on the span regardless of where it is exported.
        self.assertEqual(span._attributes["agent.identity"], "agent-x")
        self.assertEqual(span._attributes["policy.consulted"], "policy-y")
        self.assertEqual(span._attributes["outcome"], "OUTCOME_Z")
        span.end()


if __name__ == "__main__":
    unittest.main()
