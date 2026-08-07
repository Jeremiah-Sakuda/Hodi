from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Install a provider only if the process has not already configured one.
# Unconditionally calling set_tracer_provider() made span capture depend on
# module import ORDER: whichever module imported first won, and OpenTelemetry
# silently refused the loser with "Overriding of current TracerProvider is not
# allowed". Tests and hosts that install their own exporter must be able to.
def _ensure_provider() -> None:
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return  # a real SDK provider is already installed; leave it alone
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
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
