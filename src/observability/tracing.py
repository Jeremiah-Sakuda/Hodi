import os
from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Install a provider only if the process has not already configured one.
# Unconditionally calling set_tracer_provider() made span capture depend on
# module import ORDER: whichever module imported first won, and OpenTelemetry
# silently refused the loser with "Overriding of current TracerProvider is not
# allowed". Tests and hosts that install their own exporter must be able to.
def _build_exporter():
    """
    The span exporter, chosen by environment (HOD-714). Console-exported spans
    are INSTRUMENTATION, not yet an observability story: the delegation must be
    reconstructable from a durable BACKEND. When HODI_TRACE_EXPORT=cloud on a
    deployment with credentials, spans go to Cloud Trace and a whole delegation
    reads as one waterfall there; otherwise the console exporter stays the
    default, so `make demo` and the offline suite remain credential-free and
    print their spans exactly as before. The span attributes are identical
    either way — only the destination changes.
    """
    if os.environ.get("HODI_TRACE_EXPORT", "").lower() == "cloud" \
            and os.environ.get("HODI_OFFLINE") != "1":
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
            return BatchSpanProcessor(CloudTraceSpanExporter(project_id=project))
        except Exception:
            # Never let an unavailable backend break instrumentation — fall
            # back to console and keep emitting, rather than losing the spans.
            pass
    return BatchSpanProcessor(ConsoleSpanExporter())


def _ensure_provider() -> None:
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return  # a real SDK provider is already installed; leave it alone
    provider = TracerProvider()
    provider.add_span_processor(_build_exporter())
    trace.set_tracer_provider(provider)


_ensure_provider()
tracer = trace.get_tracer("hodi.observability")

def create_agent_decision_span(span_name: str, agent_identity: str, policy_consulted: str, outcome: str):
    """
    Creates an OpenTelemetry span for an agent decision carrying (a) identity, (b) policy, (c) outcome.
    """
    span = tracer.start_span(span_name)
    span.set_attribute("agent.identity", agent_identity)
    span.set_attribute("policy.consulted", policy_consulted)
    span.set_attribute("outcome", outcome)
    return span
