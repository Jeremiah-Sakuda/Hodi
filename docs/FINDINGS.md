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

### 2026-08-07 — Phase 7 Google-Toolchain & OTel Span Findings (HOD-340)

**Google-Toolchain Findings:**
1. **OTel Trace Span Design for Policy Enforcement:** Found that surfacing IAM enforcement logic natively inside OTel spans (e.g., `agent.identity`, `policy.consulted="gateway_policy_v1"`, `outcome="DENIED"`) is exceptionally powerful for audit reasoning. Rather than parsing unstructured stdout, the span itself carries the structure of the conflict boundary decision. This is precisely what a Fleet judge looks for.
2. **Antigravity's Context Window and Temporal Accuracy:** Discovered that relying on Antigravity to perfectly synthesize transcript logs over the live network can lead to "predicted" output rather than "observed" output if the agent bypasses running the physical tool chain. Setting a strict, standing `AGENTS.md` rule enforcing empirically verifiable execution (e.g., using `time` and pasting verbatim `stdout`) is necessary to prevent LLM pleasing-behavior from fabricating metrics.

---

### 2026-08-07 — Session Findings: Territory Lattice Defect, Denial Event Unification, Self-Traffic Misclassification & Gemini Model Availability Probe (HOD-106, HOD-311, HOD-312, HOD-301, HOD-320)

**Scope-Lattice Edge Case — Empty Territory (HOD-106):**
- **Defect:** `permits()` resolved an empty granted `territory` list as "no territories permitted": a request for `["US"]` against a grant with `territory=[]` was denied. An empty or absent territory list must mean UNRESTRICTED (worldwide), equivalent to `["WW"]`.
- **Companion hazard:** an empty *requested* territory slipped past territory-limited grants, because `set().issubset(anything)` is vacuously true. An empty requested territory asks for worldwide use and must be denied by a territory-limited grant.
- **Fix:** both semantics corrected in `src/resolve/evaluator.py`; truth table extended to 45 cases (cases 43–45). Cases construct the grant `Scope` directly because the test helper's `territory or ["WW"]` coerced explicit `[]` into `["WW"]` — the exact blind spot that let the defect ship.

**Denial Evidence Was Two Records (HOD-312):**
- **Defect:** a gateway denial reached Cloud Logging as an unhandled `PermissionError` stack trace (file path + line number) while the API returned a differently worded message — two code paths producing two divergent records of one denial.
- **Fix:** the gateway now raises `GatewayPolicyDenial` carrying a structured `PolicyDenialEvent` (calling SA, role, target collection, attempted filters, session context, policy consulted, rejection reason, timestamp). The event is emitted as one pure-JSON stdout line (ingested by Cloud Logging as queryable `jsonPayload`, severity WARNING) and the identical event object is returned in the API response — verified live by matching `event_id` between the HTTP response and the Cloud Logging entry.

**Self-Traffic Misclassification in the Accrual Audit (HOD-320):**
- **Defect:** the accrual audit's self-UA patterns omitted `python-requests` (the live boundary test script) and `Hodi-Latency-Test/1.0` (the timing harness), so 80 of 145 records were about to be reported as "non-self-originated" — a fabricated third-party finding.
- **Verification:** a per-user-agent, per-IP audit of all records showed every record originates from the developer's two IPs. The single browser-UA record is `scripts/audit_corpus.py` (which sends a spoofed browser UA to check bot-protected external URIs) hitting our own endpoint from the developer's IP.
- **Fix:** self patterns extended in `scripts/daily_accrual_check.py` and `src/evidence/gemma_triage.py`. **The zero-third-party-hits finding stands.** `make metrics` now regenerates `daily_crawler_accrual_metrics` in `docs/metrics.json` from the live Firestore audit.

**Gemini Model Availability Probe (HOD-301) — decision needed:**
- **Observed (2026-08-07, Vertex AI `generateContent` REST, project `hodi-2026`):** `gemini-2.5-flash` in `us-central1` returned HTTP 200 (`"modelVersion": "gemini-2.5-flash"`). `gemini-3.5-pro` and `gemini-3.5-flash` returned HTTP 404 (`Publisher model ... was not found or your project does not have access to it`) in both `us-central1` and `global`.
- **Repo state:** the only Gemini artifact in the codebase is a mocked client in `tests/test_vertex_gemma.py` pinning `gemini-1.5-pro` / `gemini-1.5-flash` literals; no runtime code path calls Vertex AI.
- **Implication:** the compliance matrix row "Gemini 3.5+ via Vertex AI" is not currently backed by a reachable model or a runtime integration. This is recorded as an open item, not resolved silently.

---

### 2026-08-07 (session 2) — Gemini Runtime Integration, Model Availability Probe (Corrected), Fold-Before-Containment Defect, Scheduler First Executions (HOD-301, HOD-303, HOD-005, HOD-106, HOD-107)

**Gemini Model Availability — CORRECTED probe (supersedes the earlier same-day entry):**
The earlier probe's `global` results were invalid — it used a nonexistent host (`global-aiplatform.googleapis.com`) instead of `aiplatform.googleapis.com` with location `global`. Corrected results (Vertex `generateContent`, project `hodi-2026`, 2026-08-07):
- **HTTP 200:** `gemini-3.5-flash` @ global (`modelVersion=gemini-3.5-flash`); `gemini-3.5-flash-lite` @ global; `gemini-3.6-flash` @ global; `gemini-3.1-pro-preview` @ global; `gemini-3-flash-preview` @ global; `gemini-2.5-pro` and `gemini-2.5-flash` @ us-central1, us-east4, and global.
- **HTTP 404 everywhere probed:** `gemini-3.5-pro` (also absent from the 126-model publisher catalog listing); `gemini-3-pro-preview` (listed in the catalog but 404 on generateContent).
- **Model selection:** `gemini-3.5-flash` (interpreter) and `gemini-3.5-flash-lite` (triage tier) — the newest stable non-preview 3.5-generation IDs reachable. Preview IDs excluded because they roll and judging runs to Oct 1. The hackathon's Gemini 3.5+ mandate is satisfied by running code, not a plan.

**Serverless Gemma (HOD-303, HOD-005):** `gemma-4-26b-a4b-it-maas` @ global returns HTTP 200 (observed classifying `GPTBot/1.2` → `bot`). Serverless per-token Gemma makes the fenced GPU project design unnecessary — the triage tier now calls Vertex Gemma with Ollama and heuristic fallbacks, and classified a live record (`human`) inside the deployed accrual audit.

**Fold-Before-Containment Defect (HOD-106/HOD-107, live path):** `permits()` takes ACTIVE grants, but the API handed it raw grant events. In an append-only log a revoked grant's original `granted` event is still present, so **a revoked grant would still have permitted requests on the live path**. Surfaced by the demo's natural-language beat asserting the poisoned request must be denied. Fixed with `active_grant_events()` in `src/resolve/resolver.py` (a projection of `resolve()`, preserving it as the single read path); every log reader now folds before containment; truth-table cases 46–47 cover it, including the precondition test proving raw events would wrongly permit.

**Structural property of the interpreter (HOD-301/HOD-311):** the model interprets intent, the lattice decides permission. Tests assert: an interpretation smuggling `{"permitted": true}` is REJECTED (not stripped); a maximal valid interpretation is still denied by the lattice; the recorded poisoned-fixture interpretation came back BROADER (worldwide) and was therefore denied — the injection cannot expand permission.

**Cloud Scheduler first executions (observed):**
- `hodi-daily-accrual-audit` (0 9 * * * UTC): lastAttemptTime `2026-08-07T18:42:13Z`, wrote `accrual_audits` doc `2026-08-07T18:42:14Z` with `triggered_by: Google-Cloud-Scheduler`, total_accrued_records 178.
- `hodi-nightly-teardown-trigger` (0 23 * * * UTC): lastAttemptTime `2026-08-07T18:42:12Z`, spawned Cloud Run Job execution `hodi-nightly-teardown-n8rhx`; the manual first execution `d9grm` logged `[VERIFIED NO-OP] Project hodi-gemma-2026 does not exist` and exited 0.

**Deployed natural-language path latency** (`deployed-over-network`, includes one server-side Gemini call per request): 3095.11 / 3127.29 / 3302.42 ms, avg 3174.94 ms — recorded in `docs/metrics.json`. Live outcomes observed: in-grant request permitted with receipt; broad commercial-training request interpreted as `training/proprietary_frontier/WW` and denied by the lattice.

---

### 2026-08-07 (session 3) — Cross-Buyer Leak, Two Compounding Causes, and ADK Execution Findings (HOD-311, HOD-302, HOD-330, HOD-340)

**The invariant was false in production while the repo asserted it (HOD-311):**
- **Cause A — identity from attacker-controlled input.** The buyer API used the body's `counterparty_id` as BOTH the query filter and the `session_context` the Gateway compared it against. A check that compares a claim to itself always passes. The Gateway was working exactly as designed; it was being handed the attacker's assertion as the ground truth.
- **Cause B — prefix matching in the policy.** `get_action_permission()` matched with `collection_name.startswith(permitted.split("/{")[0])`, so the entry `buyer_terms/{counterparty_id}` — written to express per-counterparty scoping — also permitted an unfiltered read of the entire `buyer_terms` collection, with `required_filter_key = None`. `denied_collections` existed in the policy data and was consulted by nothing.
- **The lesson worth keeping:** `make demo-live` passed throughout, because the debug endpoint supplies its own session context and therefore could not fail the way production failed. **A boundary test that cannot fail the way production fails is not a boundary test.** `make demo-live` now has a Part B that replays the real exploit against the production path.
- **Secondary finding:** the negotiator agent's cross-buyer refusal lived in a Python `if` inside `LicensingNegotiatorAgent`, off the enforcement path entirely. Moved into the policy check, so the agent class cannot be correct-by-comment.

**Google-Toolchain Findings — ADK (`google-adk==2.6.2`):**
1. **Deterministic multi-agent execution without an LLM is supported and undocumented-by-example.** Subclassing `google.adk.agents.BaseAgent` and implementing `_run_async_impl` yields a fully ADK-driven agent that makes no model calls. This matters for any governed system where hops are authority decisions rather than generations — it lets ADK supply lifecycle, composition, and the event stream while the decisions stay deterministic and testable. Every ADK example we found assumes `LlmAgent`.
2. **ADK's own spans compose with application spans.** ADK emits `invoke_agent <name>` spans carrying `gen_ai.operation.name`, `gen_ai.agent.name`, and `gen_ai.agent.description`; application spans created inside `_run_async_impl` nest underneath them in the same trace. A delegation across three service accounts reads as one trace with both framework and policy attributes on it — the observability story a Fleet judge wants, obtained for free.
3. **Pydantic field storage silently deep-copies shared mutable state.** `BaseAgent` is a Pydantic model, so a `dict` passed as a field is COPIED per agent: every agent mutated a private copy, the orchestrator saw none of it, and the run "succeeded" while returning empty results. Nothing errored — the transcript looked correct because each agent's own log line was accurate. Fixed by storing shared state outside the field set via `object.__setattr__`. This is a sharp edge for anyone building stateful multi-agent flows on ADK.
4. **`SequentialAgent` is deprecated in favour of `Workflow`** in 2.6.2, with the note that "Workflow cannot yet be used as an LlmAgent sub-agent" — worth knowing before building on it.

**OpenTelemetry finding:** calling `trace.set_tracer_provider()` unconditionally at import time makes span capture depend on module IMPORT ORDER — OpenTelemetry refuses the second caller with "Overriding of current TracerProvider is not allowed", and the loser's exporter silently receives nothing. Library modules should install a provider only if none is configured.
