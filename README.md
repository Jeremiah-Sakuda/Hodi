# Hodi — Creative Consent Administration Fleet

*"Your voice is in a product you never agreed to."*  
**Hodi is the knock.**

Hodi is a governed fleet of institutional agents that administers creative consent end to end: registering works with proof of control, expressing scoped terms, negotiating with buyers under confidentiality, propagating revocations across affected grants, and maintaining an audit record that never overclaims.

---

## Technologies Used

- **Antigravity SDK & ADK**: Built using Antigravity for pair-programming and fleet orchestration; runtime multi-agent delegation branches to ADK + OpenTelemetry SDK per [docs/antigravity/decision.md](file:///Users/jerem/Desktop/2025%20Fall%20Projects/2026%20Fall%20Projects/Hodi/docs/antigravity/decision.md).
- **Gemini 3.5 Pro & Flash**: Gemini 3.5 Pro (`gemini-1.5-pro`) for scope reasoning and term interpretation; Flash (`gemini-1.5-flash`) for high-volume log triage with pinned model ID literals.
- **Gemma**: Gemma model tier for initial crawler access log triage before Gemini evaluation.
- **Google Cloud Platform**: Cloud Run (Services + Jobs), Firestore Native append-only event log, Cloud Scheduler, Cloud Logging & OpenTelemetry Trace.
- **Build & Compliance Toolchain**: Tracked in [docs/BUILD-LOG.md](file:///Users/jerem/Desktop/2025%20Fall%20Projects/2026%20Fall%20Projects/Hodi/docs/BUILD-LOG.md).

### Antigravity Verification Decision (HOD-020 Quote)

> **Assertion:** *From a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying (a) the invoking agent's identity, (b) the policy consulted, and (c) the outcome.*  
> **Observed Result:** Headless Cloud Run Job `hodi-antigravity-harness-2l2ql` executed under SAs `agent-delegator@hodi-2026.iam.gserviceaccount.com` and `agent-worker@hodi-2026.iam.gserviceaccount.com`. Native `google.antigravity` server module unavailable for headless multi-agent delegation -> **FAIL -> Branch to ADK (Google Agent Development Kit / OpenTelemetry SDK)**.

---

## Quickstart & Verification Commands

```bash
# Verify scope lattice partial order and 42-case containment truth table
make verify-scopes

# Run compliance check against PRD §4, §2 matrix, and prose
make compliance

# Run test suite
python3 -m unittest discover -s tests
```

---

## Live Services & Proof Endpoints

- **Evidence Endpoint (HOD-008)**: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app`
- **Robots Policy**: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/robots.txt`
- **Hodi Consent Terms**: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json`
- **Registered Works**: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/works`
- **Canaries Index**: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app/canaries`
