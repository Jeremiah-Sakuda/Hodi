# GATE.md — Decision Gates and Pre-committed Consequences

This document records the pre-committed decision gates for Hodi. All dates and deadlines are recorded in **UTC**.

---

## 1. Aug 8, 2026 — Antigravity Verification Boolean (HOD-020)

**Assertion:** From a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying:
1. The invoking agent's identity
2. The policy consulted
3. The outcome

**Pre-committed Consequence:**
- Executed as a boolean assertion, not a judgment call.
- Partial emission is a **fail**.
- **Fail → ADK**, whose tracing story is safer. Compliance is unaffected since ADK independently qualifies.
- Decision and observed result verbatim recorded in `docs/antigravity/decision.md`.

---

## 2. Aug 14, 2026 — Checkpoint with Numeric Pass Bar (HOD-006)

**Pass Bar:** If fewer than **6** of the following **8** requirements have passed their acceptance criteria by end of day (23:59 UTC):
- HOD-301
- HOD-310
- HOD-311
- HOD-312
- HOD-313
- HOD-320
- HOD-330
- HOD-331

**Pre-committed Consequence:**
- Immediately invoke the §7 abort ladder on Aug 14.
- Abort order: Gemma Vertex proof → redistribution evidence class → canary class → artist console polish → verbatim-match class.
- Aug 14 is the last day cuts are cheap. Every item on the ladder is a feature or a bonus, never documentation.

**VERDICT — recorded 2026-08-14:** **PASSED, 8 of 8.** All eight requirements have passing acceptance criteria in the offline suite (256 tests green), `make demo` beats, and the deployed-path proofs recorded in `docs/metrics.json`. The abort ladder is **not** invoked. Evidence: HOD-301 (Beat 4B + `natural_language_license_path` metrics), HOD-310/311/312 (conflict-wall suite + `make demo-live` 6/6 denials), HOD-313 (poisoned-fixture beat + route coverage), HOD-320 (evidence engine + lint suite), HOD-330 (registry discovery tests incl. non-disclosure), HOD-331 (fold re-hydration tests).

---

## 3. Aug 22, 2026 — Recording-Ready Gate

**Question:** *Can I record the video from what exists on my machine today?*

**Pre-committed Consequence:**
- Feature freeze at 23:59 UTC regardless of the answer.
- Focus shifts entirely to documentation, video editing, and final bonus assets.

**AMENDED by owner decision — 2026-08-14 (see §4):** the Aug 22 feature freeze is **lifted** for the judge-feedback implementation scope (HOD-701 through HOD-714) by the owner's explicit authorization. The recording-ready *question* stands and moves with the work: the video is recorded from a known-good revision after the feedback scope lands, and every on-camera duration is re-measured on that revision before recording (Observation vs. Prediction Rule). No other scope is unfrozen — the §7 cut list and non-goals are unchanged.

---

## 4. Aug 14, 2026 — Owner Decision: Implement the External Review in Full

An external judge-style review of the project was received and the owner **explicitly authorized** implementing it in full. Two pre-commitments in this file blocked that scope, and both overrides are recorded here rather than resolved silently (per AGENTS.md):

1. **The PRD's banked status is lifted.** PRD v1.1 → v1.2, an *additive* amendment: a new requirement block (HOD-701 through HOD-714) covering work-scoped authorization, request-window temporal containment, assertion authority, the consent arbiter, the incident state machine and signed manifest, cryptographic provenance, execution leases, revocation idempotency, durable registry and memory bank, real workload-identity separation, the red-team drill, constrained negotiation, and durable trace export. No existing requirement is weakened or removed; the honesty invariants and non-goals are untouched.
2. **The Aug 22 feature freeze is lifted** for exactly that scope (gate 3 above, amended in place).

**What is deliberately NOT overridden:** the three honesty invariants; the fictional-adversary positioning rule; the non-goals (no takedown automation, no payments, no second front-end — incident *containment* acts only on grants and negotiations Hodi itself administers); the Truthful Build Log and Observation vs. Prediction rules — GCP-side steps authored in this scope but not executed against the live project are logged as designed-and-unexecuted, never as done.

---

## Banked Artifacts

List of artifacts finished and never reopened:
- [x] ~~PRD (v1.1 authoritative)~~ — **unbanked 2026-08-14 by owner decision (§4)**; re-banked as v1.2 once the HOD-7xx block is implemented
- [x] AGENTS.md (governance rules and invariants) — amended 2026-08-14 only where v1.2 facts changed (fifth agent, assertion authority); invariants untouched
- [x] GATE.md (decision gates and abort ladder) — verdicts and owner decisions are appended, never rewritten
