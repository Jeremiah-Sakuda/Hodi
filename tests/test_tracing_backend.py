"""
Durable trace export selection (HOD-714).

The property under test: the exporter is chosen by environment, the offline
default stays the console exporter (so `make demo` and the suite remain
credential-free), and an unavailable Cloud backend degrades to console
rather than breaking instrumentation. The span ATTRIBUTES are unchanged
either way — only the destination moves.
"""

import os
import unittest

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

    def test_cloud_requested_without_the_exporter_installed_degrades_to_console(self):
        """The Cloud Trace exporter is not a pinned dependency in the offline
        image; requesting it where it cannot be imported must fall back, never
        crash — losing spans is worse than exporting them to the console."""
        os.environ["HODI_TRACE_EXPORT"] = "cloud"
        os.environ.pop("HODI_OFFLINE", None)
        proc = tracing._build_exporter()
        # In this credential-free environment the import (or client build)
        # fails, so we land on the console exporter.
        self.assertIsInstance(proc.span_exporter, ConsoleSpanExporter)

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
