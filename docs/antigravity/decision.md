# Antigravity SDK Verification Decision (HOD-020)

**Date:** Aug 6, 2026 (Executed per pre-committed Aug 8 gate)  
**Status:** Executed boolean assertion  
**Outcome:** **FAIL → ADK Branch Taken**

---

## 1. The Assertion

> *From a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying (a) the invoking agent's identity, (b) the policy consulted, and (c) the outcome.*

---

## 2. Test Harness Setup

- **Cloud Run Job Name:** `hodi-antigravity-harness`
- **Execution Name:** `hodi-antigravity-harness-2l2ql`
- **Project:** `hodi-2026` (`us-central1`)
- **Service Accounts:**
  - Delegator Agent: `agent-delegator@hodi-2026.iam.gserviceaccount.com`
  - Worker Agent: `agent-worker@hodi-2026.iam.gserviceaccount.com`

---

## 3. Observed Output Verbatim

### Container Output & Error Log
```
================================================================================
HOD-020: ANTIGRAVITY SDK TWO-AGENT DELEGATION & OTEL SPAN EMISSION ASSERTION
================================================================================
[CHECK 1 FAIL] Unable to import Antigravity SDK module: No module named 'google.antigravity'
Delegator SA: agent-delegator@hodi-2026.iam.gserviceaccount.com
Worker SA: agent-worker@hodi-2026.iam.gserviceaccount.com

--- SPAN PAYLOADS EMITTED ---
[
  {
    "name": "agent_a_delegation",
    "agent_identity": "agent-delegator@hodi-2026.iam.gserviceaccount.com",
    "policy_consulted": "policy_rights_custodian_v1",
    "outcome": "DELEGATED"
  },
  {
    "name": "agent_b_evaluation",
    "agent_identity": "agent-worker@hodi-2026.iam.gserviceaccount.com",
    "policy_consulted": "policy_licensing_negotiator_v1",
    "outcome": "PERMITTED"
  }
]

[HOD-020 RESULT] FAIL: Antigravity SDK is not available as a headless server SDK in Vertex AI / Python runtime for multi-agent distinct service account delegation.
[DECISION BRANCH] Branching to ADK (Google Agent Development Kit / OpenTelemetry SDK) for multi-agent delegation & span tracing.
```

### Emitted OpenTelemetry Span Payload
```json
{
    "name": "agent_a_delegation",
    "context": {
        "trace_id": "0x673675f172a11be06ad2507808a05b9f",
        "span_id": "0x4d114c5b344b8b07",
        "trace_state": "[]"
    },
    "kind": "SpanKind.INTERNAL",
    "parent_id": null,
    "start_time": "2026-08-06T19:26:25.990388Z",
    "end_time": "2026-08-06T19:26:25.990509Z",
    "status": {
        "status_code": "UNSET"
    },
    "attributes": {
        "agent.identity": "agent-delegator@hodi-2026.iam.gserviceaccount.com",
        "policy.consulted": "policy_rights_custodian_v1",
        "outcome": "DELEGATED"
    },
    "events": [],
    "links": [],
    "resource": {
        "attributes": {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.44.0",
            "service.instance.id": "17a7f8fb-8612-4f27-8bd2-3c65939189c5",
            "service.name": "hodi-agent-harness"
        },
        "schema_url": ""
    }
}
```

---

## 4. Branch Taken

**ADK (Google Agent Development Kit / OpenTelemetry SDK)**.

Antigravity is retained as the primary pair-programming, system architecture, and code generation agentic SDK assistant, while **ADK + OpenTelemetry SDK** is used for headless runtime execution of multi-agent delegation, distinct service account isolation, and OpenTelemetry span tracing (HOD-340). Compliance is unaffected since ADK independently qualifies under Hackathon Compliance Matrix (§2).

---

## 5. What Phase 2 Actually Runs On Today

Phase 2 runs on **role-separated ADK Agent classes (`src/agents/`) executing Vertex AI / GenAI calls under 4 distinct GCP Service Accounts**:
- `rights-custodian-sa@hodi-2026.iam.gserviceaccount.com` (`RightsCustodianAgent`)
- `licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com` (`LicensingNegotiatorAgent`)
- `evidence-agent-sa@hodi-2026.iam.gserviceaccount.com` (`EvidenceAgent`)
- `revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com` (`RevocationPropagatorAgent`)

Each agent class encapsulates its distinct Service Account credentials, registers with the `AgentRegistry`, passes all inter-agent traffic through `AgentGateway`, and exports OpenTelemetry spans (`src/observability/tracing.py`) carrying `agent.identity`, `policy.consulted`, and `outcome`.
