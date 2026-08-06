from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Setup tracer provider
provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
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
