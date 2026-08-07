# Findings and Learnings — Hodi

Daily observations, crawler log metrics, Gemma triage rate, scope lattice edge cases, and Google-toolchain findings (Antigravity & OTel).

---

### 2026-08-06 — Canary Planting & Corpus Ownership Verification (HOD-009, HOD-105)

**Canary Plant Date:** `2026-08-06T12:40:00Z`

**Planted Canary Strings:**
1. `HODI-CANARY-20260806-PROSE-9F81A2B3C4` (Medium Essays & Technical Writing)
2. `HODI-CANARY-20260806-CODE-7639226A1B` (Public GitHub Repository `Jeremiah-Sakuda/Hodi`)
3. `HODI-CANARY-20260806-AUDIO-4C5D6E7F8A` (Electric Bass Solo Recordings & Stems)
4. `HODI-CANARY-20260806-PROSE-DRAFT-1A2B3C` (Draft Notes on Multi-Agent Consent)
5. `HODI-CANARY-20260806-AUDIO-LIVE-3C4D5E` (Live Bass Improvisation Session)

**Explicit Limitation & Boundaries:**
- **Temporal Bound:** Canary strings only protect items published *after* the planting date (`2026-08-06T12:40:00Z`).
- **No Retroactive Coverage:** Canaries cannot detect scrapes or training ingest that occurred prior to planting. Hodi structurally enforces this boundary and makes no claim of retroactive detection for pre-existing corpus access.
- **Proof-of-Control Enforcement (HOD-105):** All 3 works at `verified_control` carry stored `control_proof` records (`well_known_file`, `signed_commit`, `platform_oauth`). Two works (`work-audio-002`, `work-essay-002`) are deliberately registered at `asserted` with `control_proof = None` to ensure all 3 control tiers are available for console and API rendering from real corpus data.

---

### 2026-08-06 — Phase 1 Scope Lattice & Honesty Invariant Findings (HOD-101–107)

**Scope-Lattice Edge Cases & Rights Principles:**
1. **Per-Grant Whole-Scope Union vs. Per-Dimension Merging:** Naive per-dimension merging across multiple active grants from the same counterparty creates severe rights bugs (e.g., composing Grant A `fine_tuning` + Grant B `commercial` into commercial fine-tuning). Containment MUST evaluate per-grant across all 5 gating dimensions simultaneously.
2. **Attribution as Condition, Not Permission Gate:** `attribution_required` is an obligation condition attached to the output license terms, not a permission gate. It must never block permission evaluation in `permits()`.
3. **Use-Type Containment Directionality:** `training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference`. A `training` grant permits `human_reference`, but a `human_reference` grant denies `training`. `synthesis` is strictly incomparable.

**Standing Honesty Invariants:**
- **No Cross-Class Evidence Aggregation:** No function in `src/evidence/` or `src/console/` may return a cross-class total, sum, ranking, or score. Honest evidence classes (`crawler_access`, `canary_hit`, `verbatim_match`, `redistribution`) render independently.
- **Deterministic Replay Guarantee:** `resolve(grant_id, at=t)` sorts events strictly by `(issued_at, event_id)`. The `event_id` tiebreak is required for HOD-103 byte-stability replay; modifying the sort criteria breaks historical audit reproducibility.

---

### 2026-08-06 — Phase 2 Architecture, Conflict Matrix & Model Armor Findings (HOD-301–342)

**Conflict-of-Interest IAM Invariants:**
1. **Single Source of Truth (`src/schema/iam_policy.py`):** The IAM permissions matrix and collection scopes are declared as python data, generating `docs/architecture/conflict_matrix.md` dynamically to eliminate drift between docs and IAM configuration.
2. **Paired Positive & Negative Matrix Rule:** Every cell asserting a `DENIED` boundary MUST be tested alongside its corresponding `PERMITTED` operation in CI. A role withholding everything passes negative tests while breaking the fleet.
3. **Byte-Identical Model Armor Preservation (HOD-313):** Inbound buyer scope documents containing prompt injection are logged and flagged, but the document stored and evaluated MUST remain **byte-identical** to raw bytes received to avoid counterparty document modification disputes.
4. **Registry Silent Non-Disclosure:** `discover(role, requesting_sa)` returns `[]` (EMPTY RESULT) on unauthorized queries to prevent disclosing agent existence.
5. **Supervisor Split (HOD-341 vs HOD-342):** `TaskAbandoned` events are written strictly **BY THE SUPERVISOR**, never by the failing worker process. Looping/failing workers are deregistered from `AgentRegistry` during quarantine while the task is rerouted or degraded to complete the buyer request successfully.
6. **Widened Boundary Detection & Structural IAM Fix:** Discovered that granting `grants` read access to the negotiator (to unblock deployment) widened the boundary to collection-wide cross-buyer visibility, violating the core thesis. Fixed by expressing the required scoping filter *structurally* in `iam_policy.py` (`required_filter_key`) and strictly enforcing it in the Gateway (matching the filter against `session_context`), proving boundary integrity over the live network.
7. **Model Armor API Unavailability:** The managed Google Cloud Model Armor API is currently in restricted preview and cannot be enabled without organization-level allowlisting. Attempting to create templates yielded HTTP 403 Write Access Denied. The component was renamed to `Prompt Inspector` and relies strictly on a local regex stub. The system's security posture rests entirely on its IAM boundaries, gateway policy enforcement, and audit traces rather than a managed API guardrail.

---

### 2026-08-06 — Google-Toolchain Findings: Antigravity Multi-Agent Capabilities & Limits (HOD-020, HOD-510)

**What Antigravity Excelled At:**
- **System Architecture & Code Generation:** Exceptionally powerful agentic pair-programming assistant for defining complex Pydantic data schemas, 5D lattice partial orders, and multi-agent gateway routing logic.
- **OTel Trace Span Design:** Natively formatted and structured OpenTelemetry trace attributes (`agent.identity`, `policy.consulted`, `outcome`).

**Headless Multi-Agent Surface Boundaries & Limitations:**
- **No Headless Server Import (`google.antigravity`):** Antigravity is an IDE/pair-programming agentic assistant, not a deployable server-side Python SDK module for headless multi-agent execution in Cloud Run Jobs or Vertex AI containers.
- **No Native Per-Agent GCP Service Account Switching:** Antigravity does not support spawning sub-agents in headless server runtime where each sub-agent executes under a distinct GCP Service Account identity (`agent-delegator@...` vs `agent-worker@...`).
- **Architectural Consequence:** Runtime multi-agent execution branches to **ADK (Google Agent Development Kit / OpenTelemetry SDK)**, while Antigravity remains the primary architecture, code generation, and pair-programming assistant.

---

### 2026-08-07 — Phase 5 Live Access Log Audit, Discoverability Action Plan & Zero-Hit Finding (HOD-303, HOD-320)

**Live `crawler_access` Collection Audit (HOD-320):**
- **Total Accrued Records:** `11` (accrued since deployment on Aug 6, 2026).
- **Observed User-Agents:** `Python-urllib/3.14`, `curl/8.7.1`, `Hodi-HealthCheck/1.0` (automated health checks & verification requests).
- **Self-Deploy Check Filtering:** 100% of currently accrued records are self-originated deployment checks. Zero third-party web crawlers or AI scrapers have hit the endpoint yet.
- **Time Spread:** `2026-08-06T17:32:36Z` to `2026-08-07T01:53:49Z`.

**Discoverability Action Plan (Aug 7 - Aug 26):**
1. **Dynamic Sitemap & Robots Reference:** Implemented `/sitemap.xml` listing all registered work records and referenced in `/robots.txt`.
2. **Backlink Placement Checklist:** Placing canonical back-links across Medium profile, GitHub repository READMEs, LinkedIn, and personal domain (`jeremiahsakuda.com`).
3. **Webmaster Console Submission:** Submitting sitemap to Google Search Console and Bing Webmaster Tools for indexation.

**Zero Third-Party Scraper Access as an Instrumented Finding:**
- **The Finding:** *"I published machine-readable consent terms at a discoverable endpoint and nobody asked"* — a stronger empirical statement about the current state of AI scraper etiquette than a single caught bot would be. The absence IS the evidence.
- **Framing & Stated Limit:** `crawler_access` is treated as a **designed-and-instrumented-but-not-yet-observed** evidence class (exactly like `verbatim_match`). If third-party accrual remains zero by Aug 26, the video and paper state this empirical negative result plainly on camera rather than synthesizing fake scraper traffic.

**`verbatim_match` Designed-But-Not-Demonstrated Boundary:**
- **Surface Limitation:** `verbatim_match` relies on external completion model behavior across third-party completion APIs.
- **Ethic Boundary:** In accordance with Hodi's honesty invariants, `verbatim_match` is treated as **designed-but-not-demonstrated** in live production environments, as external completion model outputs cannot be guaranteed or forced during demonstration.
