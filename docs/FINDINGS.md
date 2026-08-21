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
1. **OTel Trace Span Design for Policy Enforcement:** Found that surfacing IAM enforcement logic natively inside OTel spans (e.g., `agent.identity`, `policy.consulted="gateway_policy_v1"`, `outcome="DENIED"`) is exceptionally powerful for audit reasoning. Rather than parsing unstructured stdout, the span itself carries the structure of the conflict boundary decision a reviewer needs to verify.
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
- **Model selection:** `gemini-3.5-flash` (interpreter) and `gemini-3.5-flash-lite` (triage tier) — the newest stable non-preview 3.5-generation IDs reachable. Preview IDs were excluded because they roll during the evaluation window. The hackathon's Gemini 3.5+ mandate is satisfied by running code, not a plan.

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
2. **ADK's own spans compose with application spans.** ADK emits `invoke_agent <name>` spans carrying `gen_ai.operation.name`, `gen_ai.agent.name`, and `gen_ai.agent.description`; application spans created inside `_run_async_impl` nest underneath them in the same trace. A delegation across three service accounts reads as one trace with both framework and policy attributes on it — an independently inspectable observability story obtained for free.
3. **Pydantic field storage silently deep-copies shared mutable state.** `BaseAgent` is a Pydantic model, so a `dict` passed as a field is COPIED per agent: every agent mutated a private copy, the orchestrator saw none of it, and the run "succeeded" while returning empty results. Nothing errored — the transcript looked correct because each agent's own log line was accurate. Fixed by storing shared state outside the field set via `object.__setattr__`. This is a sharp edge for anyone building stateful multi-agent flows on ADK.
4. **`SequentialAgent` is deprecated in favour of `Workflow`** in 2.6.2, with the note that "Workflow cannot yet be used as an LlmAgent sub-agent" — worth knowing before building on it.

**OpenTelemetry finding:** calling `trace.set_tracer_provider()` unconditionally at import time makes span capture depend on module IMPORT ORDER — OpenTelemetry refuses the second caller with "Overriding of current TracerProvider is not allowed", and the loser's exporter silently receives nothing. Library modules should install a provider only if none is configured.

---

### 2026-08-08 — Two Findings About Our Own Discipline (HOD-311, HOD-320, HOD-360)

**Fixing a bug class on one route does not fix the class.** `/api/v1/license` was hardened on 2026-08-07 after an unauthenticated cross-buyer read; `/api/v1/revoke`, three lines below it in the same file, still took no `Request` and called no authenticator, and `/internal/accrual_audit` was public and appended on every call. The lesson generalises: after fixing an authorization defect, **enumerate every sibling route and assert the property on each**, rather than fixing the instance that was reported. `make demo-live` now has a Part C that replays anonymous calls against the mutating and internal routes, because a boundary test that only covers the route that already broke will not catch the next one.

**Our own infrastructure became our "third-party crawlers".** `Google-Cloud-Scheduler` was missing from the self-originated user-agent list, so the project's own scheduled job was counted as third-party access — inflating the signature honesty finding into a fabricated positive. This was the second miss of the same kind (after `python-requests` and `Hodi-Latency-Test`), and the root cause both times was **two copies of the list in two files**. Now one module, imported by both.

**Investigating the residue changed the claim, and narrowed it.** The 10 remaining non-self records were not crawlers: 9 arrived within one second of each other from cloud IPs and included a request to `/api/v1/debug/compromised_agent_read` — a path no crawler would find interesting and no sitemap advertises. That is inspection traffic. So the honest metric is not "third-party hits" at all; it is `known_crawler_ua_matches`, which is **0**, with everything else non-self reported as *unattributed*. The metrics file carries its own `claim_limit` string saying so. A count of "requests we did not make" is not a count of crawlers, and conflating them is exactly the move this project exists to refuse.

**Evidence records are attributable, not authenticated.** `extract_client_ip` read the LEFTMOST `X-Forwarded-For` entry, which is entirely client-supplied — anyone could stamp a `crawler_access` record with an arbitrary source IP. Now reads the hop Cloud Run's front end appends. User agents remain self-declared and unverifiable, so these records evidence *that a request was made*, never *who made it*; stated in the README rather than left implicit.

**Two guarantees had guardians that could not fail.** Prompt-injection detection lived entirely inside a `@skipUnless(HODI_E2E)` class, so emptying the pattern list broke nothing in the default suite or `make demo` — Beat 4 compared only the two licensable outcomes, which are identical whether detection works or not. And the `(issued_at, event_id)` sort tiebreak was never exercised because every fixture carried a distinct timestamp. Both now have tests, and the tiebreak test was **mutation-verified** by weakening the sort and confirming it fails. The general lesson: gating a test class for a real reason (Firestore at-rest byte identity genuinely needs Firestore) can silently strand the properties in that class that had no such requirement.

---

## Named finding — The confidentiality boundary was breakable, and it was broken

**Dates:** introduced on or before 2026-08-06 · exploited and fixed 2026-08-07 · second instance of the same class found and fixed 2026-08-08
**Requirements:** HOD-311, HOD-312, HOD-360
**Status:** closed, with the exploit retained as a permanent regression test

Hodi's first invariant — *"No agent can read another buyer's terms"* — is the project's architectural thesis. It is the first row of the invariant table, the reason the fleet is four agents instead of one, and a video beat. **It was breakable over the public internet by an unauthenticated caller, and it was broken.**

**The defect.** `POST /api/v1/license` took `counterparty_id` from the request body and used that same value as *both* the Firestore query filter and the `session_context` the Agent Gateway validated that filter against. The Gateway compared the caller's claim to itself and always agreed. The `signature` field was tested only for truthiness — any non-empty string passed.

**What was exposed.** A single unauthenticated `curl`, with `signature: "NOT-A-REAL-SIGNATURE"` and `counterparty_id: "buyer-acme-2"`, returned HTTP 200 carrying that counterparty's grant id (`grant-seed-2`), its negotiated scope (`training` / `all_models`, commercial), and a signed receipt issued in that counterparty's name. Any counterparty id was substitutable; work ids and counterparty ids are discoverable from the public surfaces.

**Why the existing tests did not catch it.** `make demo-live` passed throughout. It exercised `/api/v1/debug/compromised_agent_read`, which supplies its own session context — so it could not fail the way production failed. **A boundary test that cannot fail the way production fails is not a boundary test.** The negotiator agent's own cross-buyer refusal, meanwhile, lived in a Python `if` inside `LicensingNegotiatorAgent`, off the enforcement path entirely; the class was correct-by-comment.

**A second, independent hole in the same boundary.** `get_action_permission()` matched collections by prefix, so the permitted path template `buyer_terms/{counterparty_id}` — written to *express* per-counterparty scoping — also permitted an unfiltered read of the entire `buyer_terms` collection. `denied_collections` was declared in the policy data and consulted by no enforcement code. The policy document was correct; the enforcement quietly did not implement it.

**The fix.** Identity now derives from a verified credential and never from request content: `X-Hodi-Key-Id` / `X-Hodi-Timestamp` / `X-Hodi-Signature`, HMAC-SHA256 over the **raw request body** inside a 300-second freshness window, with the `counterparty_id` read off the credential record. A body claiming a different counterparty is refused and logged as a structured `PolicyDenialEvent`. Collection matching is exact on the root segment; `denied_collections` is consulted first and is absolute; `BaseAgent` enforces the same filter rules as the Gateway; and the Gateway now **fails closed** when session context is absent, rather than skipping the comparison.

**The recurrence, one day later.** `POST /api/v1/revoke` — three lines below the fixed handler, in the same file — took no `Request` and called no authenticator. Anyone could revoke any published `work_id`; the response disclosed every affected counterparty's id and full negotiated scope; and because the log is append-only with agent SAs holding neither `update` nor `delete`, **the writes were not undoable**. Fixing the reported route instead of asserting the property across every route is what allowed it.

**What is now structural.** `tests/test_route_auth_coverage.py` enumerates the router's own routes and fails CI if any `POST`/`PUT`/`PATCH`/`DELETE` reaches an endpoint that never authenticates; exemptions must be added to a named list, in the diff, with a written reason. It is mutation-verified: adding an unauthenticated mutating route makes it fail. Revocation additionally requires an **artist** principal, so a buyer credential cannot terminate an artist's grants. `make demo-live` gained Part B and Part C, which replay the real historical exploits against the deployed service and assert HTTP 403.

**Why this is published rather than quietly patched.** A boundary that was designed, advertised, broken, and then rebuilt with the exploit retained as a test is better evidence than a boundary that never had to survive contact. The claim "no agent can read another buyer's terms" now rests on a mechanism that has been attacked, failed, and been repaired — and on a test that fails if the same mistake is made a third time.

---

## Named finding — Our own Cloud Scheduler job was being counted as a third-party crawler

**Dates:** introduced 2026-08-07 (when Cloud Scheduler was first enabled) · found and fixed 2026-08-08
**Requirements:** HOD-303, HOD-320
**Status:** closed, with a build-failing guard and a narrower claim

This project's signature empirical finding is a negative result: *"I published machine-readable consent terms at a discoverable endpoint and no crawler asked."* Its evidential value depends entirely on the third-party count being real.

**The defect.** `SELF_UA_PATTERNS` — the list of user agents belonging to our own tooling — omitted `Google-Cloud-Scheduler`. From the moment the daily accrual job began running, **the project's own scheduled infrastructure was classified as third-party crawler access.** The honesty finding was inverted into a fabricated positive, manufactured by the project itself.

**How it surfaced.** Not from a test. The README and Diagram B stated "160 accrued records, zero attributable to third parties" while the project's own documented `make metrics` regenerated `docs/metrics.json` with a larger total and a non-zero third-party count. The docs and the tool disagreed, and the first thing a skeptical reader does is run the tool.

**The root cause is duplication, and it had already fired once.** The self-UA list existed in **two files** — `scripts/daily_accrual_check.py` and `src/evidence/gemma_triage.py`. The same class of miss had occurred the previous day (`python-requests` from the live boundary test, `Hodi-Latency-Test` from the timing harness), and the fix then was to add the missing patterns to both copies rather than to remove the duplication. The comment directly above one of those lists warned that a missing pattern "inflates the third-party count into a fabricated finding." The warning was correct and did not prevent the recurrence, because a comment is not a mechanism.

**Investigating the residue changed the claim.** After correcting the list, 10 non-self records remained. They were not crawlers: 9 arrived within a single second from cloud IPs and included a request to `/api/v1/debug/compromised_agent_read` — a path no sitemap advertises and no crawler would find interesting. That is inspection traffic. Reporting it as third-party crawler access would have been precisely the fabricated finding this project exists to refuse, arrived at from the opposite direction.

So the metric changed shape, not just value. The audit now reports **`known_crawler_ua_matches`** — currently `0` — as the only figure this project will describe as crawler access, alongside `non_self_originated_requests_count` explicitly labelled *unattributed*, with a `claim_limit` string inside `metrics.json` itself stating that a count of requests we did not make is not a count of crawlers.

**What is now structural.** One list, in `src/evidence/self_traffic.py`, imported by both consumers — the duplication that caused it twice is gone. `make check-docs` fails the build if any accrual number in the README or Diagram B disagrees with `metrics.json`, so prose and tool cannot drift apart silently again. It is wired into `make compliance`.

**The general lesson.** The instrument that produces your evidence is part of your threat model, and *you* are the most likely contaminant of it. Every tool this project points at its own endpoint has to be declared, in one place, or the finding degrades quietly into its own opposite.

---

### 2026-08-08 (closing) — The Self-Traffic Class Recurred a Third Time, and Named Vendors Left the Detector (HOD-303, HOD-320)

**Third occurrence, same class.** The final verification pass surfaced `Hodi-Adversarial-Audit/1.0` — nine records, from the developer's own IP, a Hodi-branded probe — being counted as non-self-originated. That is the third time the self-traffic list has been incomplete: `python-requests` and `Hodi-Latency-Test` (2026-08-07), `Google-Cloud-Scheduler` (2026-08-08), and now this. Each previous fix added the missing entries to the enumeration. **An enumeration you must remember to update is not a mechanism**, and this project had already written that sentence about a comment before repeating the mistake with a list.

The fix is a rule, not an entry: every probe this project points at its own endpoint is named `Hodi-<something>`, so `is_self_originated()` now matches the `hodi-` prefix. A future probe is covered on the day it is written, without anyone remembering.

**Named vendors removed from the crawler detector.** The bot-signature list enumerated real companies' crawler user agents. Two problems: the project's positioning rule is that no real company appears anywhere in the repo, and — separately — an allow-list of known names cannot see a crawler it has not been told about. Replaced with generic self-identification signatures (`bot`, `crawler`, `spider`, `scraper`, `fetcher`, `indexer`). This is **not strictly broader**: a tool identifying only by framework name no longer matches, which is stated rather than glossed, because a user agent that does not self-identify as a crawler is exactly the unattributed case this project declines to promote to a finding. Verified against the live corpus: `known_crawler_ua_matches` was 0 before and 0 after.

**The headline finding is unchanged and now stands on a better base:** across 539 accrued records, **0 match any crawler signature**. 517 are this project's own tooling; the remaining 22 are unattributed browser-like agents, 21 of which arrived from cloud IPs in bursts that included requests to the debug endpoint — inspection, not crawling.

---

### 2026-08-09 — Considered and deliberately deferred: four separately-deployed Cloud Run services (HOD-311, HOD-312)

**The improvement.** Split the fleet into four Cloud Run services, each deployed with `--service-account` bound to the identity it already carries in policy — `rights-custodian-sa@`, `licensing-negotiator-sa@`, `evidence-agent-sa@`, `revocation-propagator-sa@`. That would convert the conflict-of-interest separation from an application-layer property the Gateway enforces in-process into a **runtime GCP IAM** property: a compromised negotiator process would hold no token that can read artist identity, rather than being refused by a check inside the same process it compromised. It is the only remaining technical change worth material points.

**Why it is not being done.** Three reasons, in order of weight:

1. **It is a redeploy of a working system 22 days from the deadline.** Every measured number in `docs/metrics.json` — the drill's 1113.55 ms server-side average, the accrual corpus, the live boundary 403s — was captured against the current single-process deployment. Four services means four cold-start profiles, inter-service auth on every hop, and re-measuring everything the documentation asserts. The failure mode is not "the split doesn't work"; it is "the split works and the recorded evidence no longer matches the system."
2. **The gap is already disclosed plainly, in both outward artifacts.** The README's "What Hodi will not claim" section and §2 of the Devpost description both state that the four service accounts are the identities the policy layer names, checks, and records — that they exist in GCP holding the append-only custom role — and that the deployed service is a single Cloud Run process running as one identity, with separation enforced in-process by the Gateway and not by GCP IAM at runtime. Diagram A carries the same note. An honestly disclosed architectural limit scores better than an undisclosed one and costs less than a rushed fix that invalidates the measurements.
3. **The demo video is required and worth roughly ten times more.** It is 30% of the score and a missing one is a submission-eligibility failure, not a deduction. Remaining effort goes there.

**What would change the decision.** More runway. The work itself is well-scoped — the SAs exist, the custom role exists, and the Gateway's policy table already names the four identities — so this is a deployment-topology change rather than a redesign. It is the first thing to build after the submission deadline, and it is recorded here so that it reads as a choice with a date attached rather than as something nobody thought of.

---

## Named finding — The revocation cascade selected the wrong grants, and an earlier version of this finding defended the bug

**Found:** the direction confirmed 2026-08-12 by running the full (held × revoked) matrix against an independent oracle; a partial version of this finding (2026-08-10) caught half of it and got the fix backwards.
**Requirements:** HOD-104, HOD-107, HOD-330
**Status:** fixed — selection inverted to "grants that permit the revoked use", pinned by the 25-cell matrix, redeployed

**The rule that was wrong.** `execute_revocation_cascade(work_id, R)` terminated every active grant whose held use type was in `USE_TYPE_CONTAINMENT[R]` — R and everything R *contains*, its descendants. That is backwards. A grant should be terminated iff it **permits** R, i.e. its held type H *contains* R (H is at or above R). The two rules coincide only on the diagonal (H = R) and at the top of the chain, which is the only place anything ever tested.

**What the wrong rule did.** 12 of the 25 (held × revoked) cells were wrong — 6 over-revocations and 6 under-revocations:

| held ↓ / revoked → | training | fine_tuning | rag_retrieval | human_reference | synthesis |
|---|---|---|---|---|---|
| **training** | terminate ✓ | **UNDER** | **UNDER** | **UNDER** | — |
| **fine_tuning** | **OVER** | terminate ✓ | **UNDER** | **UNDER** | — |
| **rag_retrieval** | **OVER** | **OVER** | terminate ✓ | **UNDER** | — |
| **human_reference** | **OVER** | **OVER** | **OVER** | terminate ✓ | — |
| **synthesis** | — | — | — | — | terminate ✓ |

OVER: the wrong rule terminated a grant that never permitted the revoked use — revoking `training` destroyed a `fine_tuning`-only buyer's license for a use the artist did not revoke, irreversibly under append-only. UNDER: it left a grant that still permitted the revoked use — revoking `fine_tuning` left a `training` grant able to fine-tune. The `synthesis` cells are correctly `—` (incomparable).

**And it was on camera.** The demo grant was held at `fine_tuning` and the hero beat revoked `training`: a textbook OVER-revocation. The money shot of the whole demo was the system destroying a license the artist did not revoke. The demo grant is now held at `training` (revoking `training` correctly terminates it, and the notice's `derived_scopes` show all four uses withdrawn), so the beat demonstrates a correct, non-empty cascade.

**The part worth owning.** The 2026-08-10 version of this finding found the 6 under-revocations and called the over-revocations *correct* — "the documented downward cascade." It then argued **against** inverting the rule ("wrong in both directions… breaks the documented cascade") and wrote a test, `test_revocation_reach.py`, asserting the backwards behaviour. So the previous pass hardened the bug: a test blessed it and a findings entry defended it, and the append-only-IAM commit that followed made the erroneous terminations permanent. The defense contradicted itself — it claimed `revoke training` is "the value at which walking down and walking up agree," which is only true for a grant *held at* training, while the demo's grant was held at fine_tuning, where they disagree. This entry replaces that one.

**The fix.** Selection is now `is_use_type_contained(held, revoked)` — the exact predicate `permits()` uses, so a grant is terminated exactly when it could have exercised the revoked use, and there is one definition of that relation rather than two. `tests/test_revocation_reach.py` now asserts all 25 cells against `permits()` as an independent oracle, in both directions, and `tests/test_revocation_cascade.py` exercises the propagator end to end for both `revoke training` (hits only training grants) and `revoke fine_tuning` (hits training and fine_tuning grants). Reverting the rule fails both. `derived_scopes` is unchanged: it always described what a *terminated* grant loses (R and everything R contains), which was never the bug — the bug was using it to *select* grants.

**The one limit that remains, correctly scoped now.** Terminating a grant held ABOVE R (revoke `fine_tuning`, grant held at `training`) removes the whole grant, stripping `training` too, which was not revoked. That is real, but it is the disclosed inexpressibility of a single-valued `use_type` on a chain — there is no "training but not fine_tuning" event to write — and terminating is the safe direction. It is a property of the scope model, not of the selection rule, and unlike the old over-reach it only ever touches grants that genuinely permitted the revoked use.

**The general lesson, twice over.** First: the cascade was verified at one input, and that input was the single lattice value where the wrong rule and the right rule agree — coverage over the domain is not coverage over the code. Second, and sharper: a wrong oracle is worse than no oracle. The previous pass wrote a test and a findings entry, and both encoded the misconception, so the suite went green *because* it was wrong and the documentation *argued for* the defect. An independent oracle — here, checking selection against `permits()` rather than against a restatement of the selection rule — is the only kind that can catch this.
---

## Named finding — The append-only invariant was false at runtime: the deployed process held roles/editor

**Found:** 2026-08-10, by reading the deployed Cloud Run service's runtime service account rather than the four SAs the documentation names
**Requirements:** HOD-102, HOD-311
**Status:** closed — dedicated create-only runtime SA deployed, gateway writes changed to `.create()`, verified live

**The claim.** The project's audit trail rests on one invariant: *grant history cannot be rewritten.* The Devpost description and README state it as an IAM property — a custom role (`hodiAppendOnlyGrantWriter`) that grants `create`/`get`/`list` and withholds `update`/`delete`, "so history cannot be rewritten." `scripts/deploy_gcp.sh` binds that role to the four agent service accounts, and `tests/test_grant_log_iam.py` verified they hold it.

**The reality.** Nothing executes as those four SAs. The deployed Cloud Run service ran as the **default compute service account** (`...-compute@developer.gserviceaccount.com`), which holds `roles/editor` — and `roles/editor` includes `datastore.entities.update` and `datastore.entities.delete`. So the identity that actually writes grant events could also rewrite and erase them. The invariant was true of the identities the policy *names* and false of the identity that *runs*. The existing disclosure ("policy identities, not four runtime principals") described the conflict-of-interest separation as application-layer — accurate — but a reader fairly inferred the single runtime principal was one of the four constrained SAs. It was not.

This is the ledger's own signature pattern on the foundational invariant: a stated property, a real mechanism (the custom role, correctly defined), and nothing connecting the two at the point that executes.

**A second defect surfaced fixing the first.** Binding a create-only runtime SA immediately 500'd every write — `PermissionDenied: 403`. Cause: the gateway wrote with Firestore `.set()`, which is an **upsert**. `.set()` silently overwrites an existing document, and Firestore's IAM backend classifies it as needing `datastore.entities.update` even for a brand-new document. So the "append-only" write primitive was one that both could overwrite and required the update permission. Changed to `.create()` — a true append that needs only `datastore.entities.create` and *raises* on a duplicate id rather than overwriting. For an event log with unique event ids that is strictly stronger: a colliding id is now a loud failure, never a silent replace. The daily accrual audit had the same shape (a fixed per-day doc id overwritten on re-run) and is now `.add()`, one immutable document per run.

**What is now structural.** The service runs as `hodi-runtime-sa`, holding the append-only custom role + `roles/datastore.viewer` (all reads, zero writes) + `roles/aiplatform.user` + `roles/logging.logWriter` — no role in that set grants update or delete. `tests/test_grant_log_iam.py::TestDeployedRuntimeIdentityCannotRewriteHistory` (live, `HODI_E2E=1`) reads the deployed service's runtime SA back from Cloud Run, enumerates every role it holds, expands each role's permissions, and asserts the union contains `create` but neither `update` nor `delete`. It also asserts the runtime SA is not the default compute account. The offline `TestRuntimeIdentityProvisioning` parses `deploy_gcp.sh` and fails if the runtime binding ever includes `roles/editor`, `roles/owner`, or `roles/datastore.user`. Verified live on revision `hodi-evidence-endpoint-00037-4ff`: a real signed revocation appends successfully, and the crawler-access stream keeps accruing, both under the create-only identity.

**The cost, disclosed.** The warm revocation cascade rose from ~400 ms to ~530 ms: `.create()` is existence-checked where `.set()` was not, and reads pass through the viewer role. That ~150 ms buys the invariant being enforced by IAM at runtime rather than only by the code path. All deployed-path timings were re-measured on 2026-08-10 and the figures in `docs/metrics.json`, the README and the recording script updated to match.

**The lesson.** "Enforced by IAM" has to name the identity that executes, not the identity the documentation would like to be executing. The custom role was correct, the tests that checked it were correct, and the property was still false — because nothing checked the one SA that actually ran the code.

---

## Named finding — The `signature` field was decorative, and the documentation called it signed

**Found:** 2026-08-12, by asking what verifies a receipt (nothing does)
**Requirements:** HOD-350, HOD-620
**Status:** closed as an honesty defect — labelled and disclosed; NOT closed as a feature — verifiable signing is unbuilt

**The claim.** Revocation notices, receipts and grant events all carry a `signature`. The README described "a dated signed notice, and a receipt". The Devpost text said affected grants "get signed notices with receipts". The recording script had the narrator say, on camera, "signed notices and receipts are issued."

**The reality.** The values were literals: `SIG_REVOKED`, `SIG_RECEIPT`, `SIG_REVOCATION_<grant_id>`, `SIG_GRANT_<grant_id>`. Each is derived from the document's own identifiers, so any party could produce one, and **no code anywhere verifies a signature** — a repo-wide search for verification of these fields returns nothing. The field was named after a mechanism that did not exist. On a *legal* artifact — the notice that terminates a licence and the receipt proving it was served — that is the most consequential place in the system to have gotten it wrong.

**Why it was not "fixed" by signing.** The obvious patch is HMAC; `src/api/auth.py` already computes one for request authentication. It would be wrong here. A shared secret makes a notice verifiable only by parties who could equally forge it, so the recipient gains nothing and the field starts *claiming* something. Security theatre over a legal document is worse than an honest placeholder — it invites reliance. Real signing needs an asymmetric key the recipient can verify without minting: Cloud KMS or a managed Ed25519 key, plus key distribution, rotation, and a public verification endpoint. That is a feature with an operational surface, not a rename, and it has not been built.

**What changed.** One module, `src/schema/signing.py`, now produces every `signature` value as `UNSIGNED_PLACEHOLDER:<kind>:<id>`, and states the claim limit in prose beside the code. Every call site — propagator, gateway, both receipt paths, and all four seeders — goes through it. A reader dumping a receipt, including on camera during the hero beat, sees what the field is worth. The README's "What Hodi will not claim" carries the limit and the reason HMAC is not the answer; the Devpost text and the recording narration were corrected so neither says "signed".

**What is now structural.** `tests/test_signature_honesty.py` fails if any runtime file assigns a *string literal* to a `signature=` field — so the honest prefix cannot be bypassed by typing a new `SIG_...` constant — and separately asserts that emitted receipts and revoked events carry a labelled value, and that the README disclosure is still present. Mutation-verified in both directions: a hand-written `SIG_REVOCATION_VALID` fails three tests, and deleting the README bullet fails another.

**The lesson.** A field named after a guarantee is a claim, and the name is doing the claiming whether or not anyone wrote a sentence. This one had a mechanism-shaped hole in it for the whole project and survived every review that read the *prose* rather than the *value*. The question that found it was not "is this documented correctly" but "what verifies this?" — and the answer, for any field asserting a property, should be a file path.

---

### 2026-08-12 (closing) — Known limits re-confirmed and deliberately carried

An external pass re-identified five limitations already recorded here. They are restated together so the position is legible rather than re-litigated each round:

1. **Normal licensing and revocation do not run through the supervised ADK path.** `/api/v1/license` and `/api/v1/revoke` call the propagator and gateway directly; the ADK `Runner`, Registry discovery, Supervisor and quarantine execute on the delegation path (`make demo` Beat 5B, `/api/v1/fleet/delegation_drill`) rather than on every production request. Accurate. Routing production traffic through the supervised runner is the natural next step and is not claimed as done.
2. **Four policy identities, one runtime principal.** Disclosed in the README, the Devpost text and on Diagram A. The *append-only* half of that gap was closed on 2026-08-10 (create-only runtime SA, verified live); the *conflict-of-interest* half remains application-layer, and the four-service split stays deferred with the reasoning recorded above.
3. **Fleet control-plane state is process-local**, and a timed-out worker is abandoned but continues as a daemon thread — Python cannot kill a thread. The Supervisor's contract is "the request completes and nothing unverified is written", which it meets; it is not "the worker stops".
4. **The artist console is read-only and self-service registration is incomplete.** Deliberate: revocation needs an artist credential a static SPA must not hold.
5. **Signature fields are placeholders** — see the named finding immediately above.

Also resolved this pass: a **stale duplicate `Dockerfile`** at `src/evidence_service/Dockerfile` installed from `requirements.txt` rather than the lockfile and omitted `COPY fixtures/` — the exact omission that once shipped an empty Gemini cache and 500'd the drill. Deploying from it reintroduced a fixed defect, so it was deleted and the root `Dockerfile` documents that it is the only one that builds the service. Deployment itself is now `make deploy` → `scripts/deploy.sh`, which provisions IAM, deploys with the mandatory `--service-account`, and then reads the deployed identity back and asserts it cannot rewrite history before reporting success — because the flag whose omission silently breaks the append-only invariant should not live in anyone's shell history.

---

## Named finding — A crawler did come, and the detector could not see it

**Found:** 2026-08-12 · **Requirements:** HOD-303, HOD-320 · **Status:** closed; the headline finding is restated, narrower and stronger

**The claim, for most of this project's life.** *"I published machine-readable consent terms at a discoverable endpoint and no crawler asked."* `known_crawler_ua_matches` read **0**, and that figure was presented as the signature empirical result.

**It was wrong, by one regex anchor.** The crawler signatures were generic on purpose — `\bbot\b`, `bot/`, `[-_]bot`, `bot[-_]` — to avoid naming vendors and to catch crawlers nobody has heard of. But `\bbot\b` requires a word boundary *before* `bot`, and the commonest crawler-naming convention in existence is a vendor prefix glued straight onto it. A user agent of exactly `GPTBot` matches none of the four patterns. Neither would `Googlebot` or any sibling. The detector was blind to the single most likely shape of the thing it was built to detect.

**What was actually in the log.** One record, `2026-08-11`: user agent `GPTBot`, path `/robots.txt`, `robots_txt_fetched_first: true`. A self-identifying crawler arrived, read the robots file — and **did not fetch `/.well-known/hodi.json`**, which is one request away and is where the machine-readable terms are served.

**The corrected finding is better than the null result it replaces.** "Nobody came" is a weak claim: absence of evidence, and always one un-instrumented day from being falsified. What the corpus actually supports is sharper and is the project's whole thesis in one record: **the terms are published, discoverable, and reachable in one request from the file the crawler did read — and it did not ask.** The gap between "a crawler that respects robots.txt" and "a crawler that reads consent terms" is exactly the gap Hodi exists to close, and there is now a dated observation of it rather than a negative space.

**Scale, restated honestly.** The re-audit also covered the 1074 records accrued since the last one: **1613 total**, 1572 self-originated, 41 unattributed, 1 crawler. The previously published 539 was not wrong when written — it was stale, and dated as such, which is why the audit date is a guarded field.

**What is now structural.** The pattern is `bot\b` — trailing boundary only — which catches the prefix-glued family without naming any vendor, preserving the positioning rule that no real company appears as a violator. `make check-docs` already fails the build when the README, Diagram B or the Devpost text drift from `metrics.json`, and it caught all ten stale figures the moment the audit was re-run.

**The lesson.** A detector that has never fired is not evidence of absence; it is an untested branch. This one had produced the project's headline number for a week without a single positive control — no test ever asserted that a known crawler user agent *matches*. The guard for a null result has to be a case that makes it non-null, or the null is just the code path nobody exercised.

---

### 2026-08-14 — Implementing the External Review: Google-Toolchain Findings (HOD-706, HOD-711, HOD-714)

The readiness-review build touched three Google surfaces materially. Recording what a toolchain owner would want, per the HOD-509 charter.

**Cloud KMS asymmetric signing is the right primitive for a legal artifact, and the ergonomics reward doing it properly.** ECDSA P-256/SHA-256 `asymmetric_sign` takes a *digest*, not the message, so the canonicalization contract lives entirely on our side — one `canonical_json_bytes` (sorted keys, minimal separators, UTF-8) shared by signer and verifier, and the signature is computed over `SHA-256(canonical(doc-without-signature))`. The clean part: verification needs only `get_public_key`, so `hodi verify` and the `/verification-key` endpoint hand a recipient everything and Hodi nothing it could forge with. The honest boundary a demo forces: the deployed key is durable authority, but a credential-free `make demo` cannot reach KMS, so the offline signer is an in-process Ed25519 key **labelled `ED25519-EPHEMERAL` in every envelope** — the alg tag makes "mechanism demonstration" and "production provenance" impossible to confuse, which matters when the same verify path runs in both. Recommendation to the KMS team: the get-public-key → verify round trip is genuinely one-function-each; the gap is a canonicalization story — a documented "sign a JSON document" recipe would save every team reinventing the digest-over-canonical-bytes step and getting the exclusion-of-the-signature-field subtlety wrong.

**Per-database IAM conditions are the cleanest way to make a conflict boundary a credential boundary — on paper.** Firestore named databases plus an IAM condition `resource.name.endsWith('/databases/<db>')` express "this SA can read only its domain's database" declaratively, and it generates straight from the same policy dict the gateway reads. Stated limit, honestly: this was **scripted and not executed** against the live project this session (no gcloud auth in a coding session), so the E2E assertion — impersonate the evidence SA, read the identity database, expect `PermissionDenied` — is written and skipped, not green. What a reviewer should take from that: the boundary is real in code and in the provisioning script, and the proof is one `HODI_E2E=1` run away, but it is not claimed as deployed.

**OTel → Cloud Trace is a one-line processor swap, and the discipline is keeping attributes exporter-independent.** The audit attributes (`agent.identity`, `policy.consulted`, `outcome`) are set on the span regardless of destination; only the `BatchSpanProcessor`'s exporter changes (`ConsoleSpanExporter` → `CloudTraceSpanExporter`), gated on `HODI_TRACE_EXPORT=cloud` and a non-offline environment. The failure mode worth flagging: an unavailable exporter must degrade to console, never throw — losing a delegation's spans to a backend hiccup is worse than printing them. The Antigravity finding from Aug 8 stands unchanged (no headless multi-agent surface; ADK + OTel carry the three required attributes), and this makes the "durable backend, not just console" half of the observability story real without touching the span schema.

**Assertion authority as a second policy plane.** The most reusable idea from this build for the broader agent-systems audience: zero trust is usually framed as data access ("who may read X"). Applying the identical mechanism — data-declared policy, gateway-enforced, structured denial — to *epistemic* authority ("who may CLAIM X") cost almost nothing to add beside the existing collection policy, and it is what lets a downstream adjudicator's conclusion be reproduced rather than trusted. The structural refusal composes with the schema: the claim a role must never make (training membership) simply has no assertion class, so it dies at construction before the authority check runs.

---

## Named finding — The fallback that hid the pollution that hid the fallback

**2026-08-14.** Two defects propped each other up for a week, and neither was visible while the other stood.

**The first.** `_build_firestore_client()` ended `except Exception: return None`, and the gateway treats a missing client as its offline path. So in a deployment without working credentials, the gateway did not fail — it served an empty in-memory dict as though it were the append-only grant log. A licensing request would be answered from zero grants ("you hold no licence here") and a revocation would write into a buffer that dies with the instance. Both return HTTP 200. **A decision computed against phantom state is the most dangerous output this system has, and it is indistinguishable from a healthy one.** An external review flagged it as a risk; it was not a risk, it was the behaviour.

**The second.** Twenty-five test `setUp` blocks ended with `addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))`. `make test` sets `HODI_OFFLINE=1` for the whole run, so that cleanup did not restore the previous state — it *deleted a variable the rest of the suite depended on*. From the first such test onward, every later test ran with offline mode un-declared.

**Why neither was visible.** A test that had lost the flag still got the in-memory path — because the gateway failed open. It reached the right behaviour for the wrong reason. And the fail-open never looked wrong in CI, because the polluted suite exercised it constantly and passed. Each defect supplied the other's alibi.

The moment storage began failing closed, eight tests errored immediately. The instinct in that situation is to assume the new change is wrong; it was not. The change had removed the alibi.

**What is now structural.** Offline is a **declared** mode, never an inferred one: `HODI_OFFLINE=1` returns the in-memory path, and anything else raises with the escape hatch named in the error text (a fail-closed error that does not say how to run offline gets "fixed" by re-adding the fallback). `tests/offline_env.py` saves and restores, and `tests/test_offline_env_hygiene.py` fails the build on any cleanup that pops the flag.

**The lesson, and it generalises past this repository.** A fallback does not only weaken the property it bypasses — it *suppresses the signal* that would have revealed everything else depending on that property. Ask of any `except: return <benign default>`: if the thing I am defaulting past were broken, what would tell me? If the answer is "nothing, because this default is indistinguishable from success", the default is not resilience. It is a permanently disabled alarm. This project has now found the same shape four times — `|| true` on infrastructure commands, the session-context check that only ran when the caller cooperated, the crawler detector that had never fired, and this.

### 2026-08-14 (session 2) — Google-Toolchain Findings: Workload Identity Federation and OIDC Role Derivation (HOD-717, HOD-720)

**Cloud Run service-to-service OIDC is the cleanest available answer to "which agent is calling", and the mapping direction is what makes it safe.** A caller presents a Google-signed ID token; the receiver checks issuer, audience (its own URL — this is what stops a token minted for another service being replayed), expiry and `email_verified`, and then looks the role up **from the verified email**. The direction matters more than the checks: the caller never states its role, so there is no field to lie in. Implementation note worth passing on: `google.oauth2.id_token.verify_oauth2_token` handles signature and audience, but the issuer allow-list, the `email_verified` requirement and the email→role mapping are all yours, and all three are load-bearing — a token with a valid signature and an unverified email establishes nothing. Making the verifier injectable meant every one of those rules could be unit-tested offline while the signature check stays delegated; the offline suite therefore proves the rules and honestly does not prove the cryptography.

**Workload Identity Federation removes the credential a release workflow would otherwise have to hold.** `google-github-actions/auth@v2` exchanges GitHub's OIDC token for short-lived Google credentials, so the live-verification workflow needs no service-account JSON key in a repository secret. That matters for this project specifically: a long-lived key sitting in CI is the same defect class as everything else in this ledger — a credential that outlives its purpose, where nothing fails if it leaks. Stated limit: the pool and provider are not configured, so the workflow is authored and has never run, and `deployment_status.json` records exactly that.

**The pattern the two share, and the one I would hand to another team.** Both are cases where the platform will give you a *verified fact* (this token belongs to that service account; this workflow belongs to that repository) and your job is to derive authority from the fact rather than accept an assertion alongside it. Every remaining weakness in this system's identity story is a place where something is still asserted in-process instead of derived from a verified fact — which is why in-process callers now carry that as an explicit category rather than a caveat in prose.

## Named finding — `verbatim_match` was a rubber stamp, and the README said the checking code existed

**Found:** 2026-08-14, during an ideation review of where one more model could go — the answer was "nowhere; fix this instead"
**Requirements:** HOD-320, HOD-350, HOD-620
**Status:** closed — both methods now check, the false sentence is corrected in place

**The defect.** `EvidenceEngine.process_verbatim_match(prompt, generated_output, work_id, source_uri)` **read neither `prompt` nor `generated_output`.** It built a constant detail string — an f-string with no interpolation fields — and emitted an `EvidenceRecord` unconditionally. `process_redistribution(work_id, mirror_uri)` was worse: it took no content parameter at all, so it could not have verified a redistribution even in principle, and emitted one on every call.

**The test blessed it.** `tests/test_evidence_engine.py` passed `generated_output="Verbatim essay excerpt"` — sharing nothing with `work-essay-001` or any other registered work — then asserted a record **was** produced, checking only `class_name` and `claim_limit`. A test that cannot distinguish a match from a non-match is not a test of a matcher; it is a signature on the rubber stamp.

**And the README claimed otherwise.** `README.md` stated, inside **"What Hodi will not claim"**: *"The class exists in the schema and the checking code exists; no live hit is claimed."* There was no checking code. That sentence sat among deliberately exact neighbours — 1613 accrued records with 1 crawler match, 4-of-12 measured lint coverage, `UNSIGNED_PLACEHOLDER` — and borrowed their credibility. It is the third time this project has published a claim its mechanism did not support, and the first where the false clause was inside the honesty section itself.

**What mitigates it, stated so the correction is not overstated either.** `EvidenceEngine` has **no production caller** — it is imported only by two test files — so no such record was ever minted on the live service. The defect was latent, not exploited. That is also precisely why it was safe to fix days before a recording.

**The fix, and why it is deliberately not a model.** `src/evidence/verbatim_probe.py` performs a longest-contiguous-token-run comparison over stdlib `difflib` against a **registered passage** (`fixtures/work_passages.json`), with a fixed published threshold of 12 normalized tokens. A run below threshold returns `None` — the outcome the old code could not produce. `process_redistribution` gained `mirror_content` and `canary_string` and now requires either exact canary containment or such a run.

**"Verbatim" means exact, so an embedding would have been the wrong instrument.** Routing this through a similarity model would let a paraphrase mint a record typed `verbatim_match` — the same category error as naming a constant `SIG_REVOKED` and calling it a signature. The check is deterministic, offline, credential-free and explainable in one sentence. A model was considered for this slot and rejected on those grounds.

**What is now structural.** Three tests assert the negative — unrelated output, a paraphrase, and a bare mirror URI each produce **no record** — and the positive case asserts the detail string describes *that* match (token count and matched-run hash) rather than a constant. Mutation-verified: restoring unconditional emission fails them. The README bullet now states what the check does, what it does not establish (co-occurrence of text, never training-set membership), and carries the dated correction of the sentence it replaced.

---

## Named finding — the overclaim lint rejected 4 of 12 paraphrases, and now rejects 12

**Found:** 2026-08-08 (measured), addressed 2026-08-14 · **Requirements:** HOD-320, HOD-350 · **Status:** improved and re-measured; the schema remains the invariant

**The disclosed weakness.** `OverclaimLint` is nine regexes. Measured against a 12-paraphrase probe set seeded from phrasings it was deliberately not written against, it rejected **4**. That number was published rather than hidden, and the README said plainly that the schema is the invariant and the lint only reduces the chance of a bad sentence.

**The addition.** `src/evidence/semantic_backstop.py` embeds candidate text with `gemini-embedding-001` (pinned; probed HTTP 200 on 2026-08-14, `text-embedding-005` documented as fallback) and compares it to plain-language anchors. Measured coverage went **4/12 → 12/12**, with **0 of 9** legitimate texts falsely refused.

**Why a model is admissible here and nowhere else.** Hodi's standing rule is that a model never decides anything. This one decides nothing about rights, grants, or evidence classification — it inspects text *Hodi itself is about to emit*, and it runs only **after** every regex has already declined to reject. So the composition is monotonic in strictness: there is no input for which enabling it PERMITS text the regexes would have blocked. A wrong embedding therefore yields a false refusal — Hodi emits the deterministic template instead of a drafted notice — never a false permission. `tests/test_semantic_backstop.py` asserts that property directly rather than describing it.

**The bug this design was corrected for, before it shipped.** A one-sided similarity threshold **refused** *"This grant is hereby terminated. This revocation does not un-train the model."* Embeddings handle negation poorly: a sentence that DENIES the forbidden claim sits close to it. That was not hypothetical — every drafted notice is *required* to contain "does not un-train" (`src/llm/notice_drafter.py`), so the naive backstop would have refused the exact text the system exists to produce, degrading every notice to the template. The fix is nearest-anchor classification: a candidate is refused only if it is near a forbidden claim **and nearer to it than to anything Hodi is legitimately supposed to say** (`PERMITTED_CLAIM_ANCHORS`). `test_negated_claims_are_not_refused` keeps it fixed.

**Both figures stay published.** `metrics.json` records `paraphrases_rejected: 12`, `rejected_by_regex_alone: 4`, and `rejected_by_semantic_backstop: 8`, because the second layer depends on a model that can regress or become unreachable — in which case coverage falls back to 4 and the backstop disables itself rather than guessing. `make check-docs` guards **both** numbers; claiming the fallback is 12 fails the build. Vectors are recorded from live Vertex into `fixtures/embedding_cache.json` by `make embedding-cache`, so `make demo` stays credential-free.

**What has not changed.** The structural guarantee is still the schema: `EvidenceRecord` has no field capable of expressing training-set membership, and that — not the lint — is what stands between Hodi and the claim.

---

## Named finding — the recording script would have failed on camera, and its own banner had said so for days

**Found:** 2026-08-14 (by executing it) · **Requirements:** HOD-730 · **Status:** fixed, verified live, guarded

**What happened.** `docs/VIDEO-SCRIPT.md` carried a banner at the very top warning that `work_id` had become mandatory on `/api/v1/license` and `/api/v1/license/natural`, and that every license body below had to add it *"or it is refused **422** before timing even starts."* Three of the four on-camera command bodies still omitted it. Run against the deployed service (revision `00045-dkz`) on 2026-08-14, Beat 3 and the hero's Frames A and C each returned:

```
HTTP 422  {"type":"missing","loc":["body","work_id"],"msg":"Field required"}
```

`ScopeRequest.work_id` and `NaturalScopeRequest.work_id` are required with no default. The banner had been correct since the build that introduced the change. Nothing checked it, so nothing fixed it — **a warning is not a mechanism**, which is the fourth distinct restatement of this project's most-repeated defect class, and the first where the cost would have been a lost take rather than a red test.

**A second failure the banner did not predict.** With `work_id` added, the hero's Frame A *still* returned `permitted: false`. Its scope hardcoded `valid_from: "2026-08-09T00:00:00Z"` while `make recording-prep` seeds the demo grant with `valid_from = now`; `permits()` requires the request window to be contained in the grant window, so a request opening five days before the grant is correctly refused. Frame A is the frame whose entire job is to show the licence **granted** — a false there is not a slow beat, it is no hero beat at all. This one was invisible to the banner because it is not a schema error: the request was well-formed and the answer was right.

**A third, in the opposite direction.** The script instructed the presenter to say, on camera, that the `signature` field reads `UNSIGNED_PLACEHOLDER`. It no longer does. Cloud KMS signing shipped, and the deployed service returns `KMS-ECDSA-P256-SHA256:hodi-provenance/cryptoKeyVersions/1:…`. Narrating the placeholder would have stated something the screen contradicted **and** discarded the strongest provable claim in the submission. The placeholder was honest while nothing could verify anything; it was retired by building the thing, and the narration had not followed. Verified the same day: the notice the cascade issues verifies with the public key alone (`VERIFIED`, exit 0), and one changed byte fails it (`VERIFICATION FAILED`, exit 1).

**And the drift had reached the README, from this session's own work.** The README's deployed-path sentence read *"revocation cascade 3049 ms cold / 534 ms warm average"* while `docs/metrics.json` — named as its source one clause earlier — said 2263 / 736.6. The metrics file had been regenerated hours before after a real regression; the prose citing it had not been. Every other published figure in the README was guarded. Latency figures were not, so that is where the drift went: nothing breaks when a latency number is wrong, and a wrong one is always plausible.

**What is now structural.**
- `tests/test_recording_script_contract.py` parses `docs/VIDEO-SCRIPT.md`, derives the route→model table **from `src/api/buyer_api.py`** rather than transcribing it, and fails if any scripted request body omits a required field of the route it posts to. It also fails on a hardcoded `valid_from` in a request body, and on any instruction to narrate `UNSIGNED_PLACEHOLDER` as current. Mutation-verified against all three real defects: each reintroduction fails the suite.
- `check_deployed_timings()` in `scripts/check_doc_metrics.py` binds every latency figure in the README to `docs/metrics.json`, and additionally requires the sentence to name the revision the measurement came from — a latency number without a revision is a memory, not an observation. Mutation-verified by restoring the stale 3049/534 pair.

**What is not guarded, and is stated instead.** Whether a scripted request is *permitted* depends on live grant state, which no static check can know; that remains the job of `make recording-prep`, which reports both grant statuses from the fold, the affected-set size, and the predicted cascade cost before a take.

---

## Named finding — a reviewer concluded the autonomous audit was not scheduled, and the repository had earned that reading

**Found:** 2026-08-14 · **Requirements:** HOD-320 · **Status:** no code defect; documentation trail added

**What happened.** An external reviewer, checking whether Hodi's incident pipeline actually runs unattended, grepped `scripts/daily_accrual_check.py`, found no scheduled trigger referencing it, and reported that the project's headline autonomous loop "is **not** wired to any scheduled trigger."

**The claim was false, and the reading was fair.** Cloud Scheduler job `hodi-daily-accrual-audit` had fired that same morning — `AttemptFinished 2026-08-14T09:00:58Z`, *"Original HTTP response code number = 200"* — against `GET /internal/accrual_audit` on the deployed service, which runs the Gemma triage and appends one immutable row to `accrual_audits`. But the scheduled work lives in `src/evidence_service/main.py`, and the file that carries the *name* of the daily audit is the manual metrics path, deliberately unscheduled. Two surfaces shared a name and shared no reference to each other. A reviewer who greps the obviously-named file and believes the result is doing exactly the right thing.

**Fix.** `scripts/daily_accrual_check.py` now opens by naming the scheduled endpoint, its job, its schedule, its identity requirement and where its rows land — and says plainly that it is not the scheduled path. The `scheduled_jobs` entry in `docs/deployment_status.json` now cites the Cloud Logging execution record directly rather than only the metrics rows it produces, so the claim is checkable by a reader who has not read this document.

**The lesson, which is not about scheduling.** Every other finding here concerns a claim stronger than its mechanism. This is the inverse: a mechanism stronger than its trail. It cost nothing to fix and would have cost a category of credit that had actually been earned.

---

## Named finding — the public manifest was serving no canaries and no proof of control, and the proof route answered HTTP 500

**Found:** 2026-08-14, by the live release-verification workflow's first execution · **Requirements:** HOD-718, HOD-731 · **Status:** fixed, deployed, verified live, guarded

**What was live.** `GET /works` on the deployed service returned five works of **five fields each**. No `canary_string` on any work — the canaries are the entire mechanism behind the `canary_hit` evidence class. No `control_proof` on `work-repo-001`, the project's one `verified_control` work, while the README's opening sentence says Hodi registers works *"with proof of control"*. And `GET /works/work-repo-001/proof` — the endpoint whose only job is to serve that proof — returned **HTTP 500**.

**The cause.** `get_registered_works()` unioned the committed seed corpus with the rows persisted in Firestore as `{**seed, **registered}`: a **row-level** replacement. The persisted rows carry `work_id`, `artist_id` and `control_tier`. The seed carries those plus eight more. So every persisted row silently deleted eight fields from the public manifest, and the proof route then indexed `work["control_proof"]` on a row where the key was absent rather than `None`. A comment directly above the union explained why replacement was correct — *"the seed is a starting point, not an override of what an artist actually did"* — and the reasoning is right about override and wrong about erasure. **Absence is not an assertion.**

**Why it survived this long.** `scripts/verify_manifest.py` had been reporting all of it correctly for as long as it was true. It is wired into `make verify-manifest`, and `make verify-manifest` is in `.github/workflows/verify-live.yml` — the workflow that had been authored and **never executed**, because its Workload Identity Federation pool did not exist. The check existed, named the defect precisely, and had never been run against the thing it checks. Two external reviewers read `live_release_verification: scripted_not_executed` as a modest gap in production-readiness storytelling. It was hiding a live defect on a public endpoint that the submission's opening claim depends on.

**The fix.** The union is now field-by-field: a persisted value overrides the seeded one, and a persisted row that is *silent* about a field inherits it. A persisted explicit `None` is treated as unset rather than as a deletion, because Firestore rows carry explicit nulls and the other reading reintroduces the same bug. `.get()` replaces `[]` in the proof route, so a missing proof is a statable `"unverified"` answer rather than a stack trace.

**And the merged row does not pass the borrowed fields off as registered.** Every key inherited from the seed is named in `seed_supplemented_fields` on the row itself. A reader of the live manifest can see that `work-repo-001` is `source: registered` and that nine of its fields came from the committed seed. Fixing an erasure by silently filling the gap would have been the same defect class one layer up.

**Verified live after deploying:** all five works carry their canary; `work-repo-001` carries its `control_proof`; `GET /works/work-repo-001/proof` returns **HTTP 200** with the signed-commit evidence.

**What is now structural.** `tests/test_manifest_merge.py` — eight tests asserting that a partial persisted row keeps the canary and the proof, that a persisted value still wins, that an explicit `None` does not erase, that borrowed fields are named, and that the proof route answers instead of raising. Mutation-verified: restoring the row-level replacement fails four of them by name.

---

## Named finding — a capability recorded as "scripted, never run" was hiding four live defects, and its first run found all of them

**Found:** 2026-08-14 · **Requirements:** HOD-720 · **Status:** executed, green, recording its own result

**The gap as it was read.** `docs/deployment_status.json` marked `live_release_verification` as `scripted_not_executed`, disclosed plainly: the workflow existed, its Workload Identity Federation pool did not, so it had never run. Two external reviewers treated this as a modest gap in the production-readiness story — *"authored but explicitly never executed"* — and one listed closing it among four things separating the project from a perfect score. Both were reading it as a missing proof of things already true.

**What it actually was.** The workflow is the only thing that runs `make verify-manifest`, the `HODI_E2E` suite and the KMS checks against the deployed service. Nothing else runs them anywhere. Its first four attempts failed, and **not one failure was CI plumbing**:

1. **The public manifest was serving no canaries and no proof of control**, and `/works/{work_id}/proof` answered **HTTP 500** on the one `verified_control` work. Recorded separately above; `verify_manifest.py` had been reporting it correctly for as long as it was true.
2. **`test_buyer_api_e2e` was asserting nothing.** Its license bodies omitted the now-required `work_id` and `counterparty_id`, so both signed-request tests received **422** and never exercised scope resolution or receipts. The same defect, in the same week, as the recording script — and for the same reason: nothing ran it.
3. **`test_discovery_does_not_disclose_deregistered_agents` asserted `len(found) == 1`** against `AgentRegistry()`, which now defaults to the durable append-only store. It passes only against an empty registry, so it failed on a system behaving exactly as designed. An oracle that only holds in a world nobody deployed.
4. **`cloudresourcemanager.googleapis.com` had never been enabled on the project.** The append-only IAM proof reads the project policy, and it had only ever run from a laptop, where *user* credentials take a different quota path. From a service identity it could not run at all. A check that passes only under one particular set of credentials is not a property of the system.

**And the workflow itself contained a defect of the class this project exists to remove.** Its KMS step required `roles/cloudkms.signer` on the CI identity — **the power to forge any Hodi receipt** — in order to sign a receipt and then verify the signature it had just made. A closed loop: it proves CI can use a key, not that the deployed service is honest. It also set `HODI_SIGNING=kms` without `HODI_KMS_KEY_VERSION`, so it could never have run. Replaced with a check that holds `publicKeyViewer` only and proves the two things a recipient actually depends on: the public key `/verification-key` **advertises** is byte-identical to the one KMS holds, and a real notice the deployed service issued still verifies under it while one changed byte does not. That second check also catches a key version rotated away from already-published receipts.

**The federation, and the narrowing.** `scripts/setup_release_verification.sh` creates the pool, an OIDC provider **attribute-conditioned to this repository alone**, and a verifier service account bound to exactly one `principalSet`. This project made the unconditional-binding mistake once already, on the per-domain Firestore grants, where a condition narrowed nothing because a broad grant sat beside it. Here the same mistake would not have failed a test — it would have issued tokens for this project to any repository on GitHub. So the script reads the provider condition and every impersonation member back out of IAM and refuses to exit 0 unless the narrowing is present, refuses if the verifier holds `owner`, and refuses if it can impersonate any domain identity other than the single one it needs in order to prove that identity is denied.

**And the generated table was not being generated.** The deployment-status table in `README.md` is marked GENERATED and says not to hand-edit it. Nothing regenerated it and nothing compared it — so recording a promotion in the JSON would leave the README showing the old state and the old date, which is the drift that file exists to prevent, occurring inside the artifact it produces. It was already stale by four rows. `deployment_status.py --write-readme` now regenerates it, `check_doc_metrics.py` fails the build when it disagrees, and the live workflow regenerates it as part of its write-back.

**Where it landed.** Staging green, then production green with write-back: [run 31827960181](https://github.com/Jeremiah-Sakuda/Hodi/actions/runs/31827960181) recorded six capabilities as verified against revision `00046-fmn`, **including itself**, and the evidence is the run URL. `scripted_not_executed` went from two capabilities to one.

**The lesson, and it is not about CI.** This project's discipline is that a claim must be derived from its evidence. `scripted_not_executed` was an honest label, and honest labelling made the gap comfortable enough to leave. **A check that has never run is not a weaker check — it is an unknown**, and four of the things it turned out to be checking were false.

---

## Named finding — the durable trace backend could never have worked, and three separate mechanisms each reported success while it didn't

**Found:** 2026-08-14 · **Requirements:** HOD-714, HOD-732 · **Status:** executed, verified live against a real trace id, guarded

**The setting was a no-op.** `HODI_TRACE_EXPORT=cloud` selected a Cloud Trace exporter, and `opentelemetry-exporter-gcp-trace` **was not in `requirements.lock`**. The import therefore failed, the code caught the exception, and the `except` block was a bare `pass`. For the entire life of that setting the "durable trace backend" could only ever have been the console exporter. The service started healthy, spans kept printing to stdout, and nothing anywhere said otherwise. This is why the capability was honestly marked `scripted_not_executed` — but that label described a script that had not been run, when the truth was a mechanism that could not have run.

**Then it still didn't work, for a completely different reason.** With the package pinned and the exporter constructing without error, four real requests produced **zero** traces. `BatchSpanProcessor` flushes on a background thread, and Cloud Run throttles a container's CPU to approximately nothing between requests, so that thread is never scheduled. No error, no warning, no spans. Fixed with one bounded `force_flush` inside the request, where CPU is guaranteed — a dropped span is an observability loss, a hung request is an outage, so the flush has a 2-second ceiling.

**And then the measuring instrument turned out to be broken.** Having found zero traces, the obvious conclusion was that export was still failing. It was not. `cloudtrace.googleapis.com/v1/…/traces` **`LIST`** returned 0 results for a window in which a span demonstrably existed — proven by writing a known span via `v2 batchWrite` and fetching it back by id, which **found** it, while the same span was absent from `LIST` over the same window. **The oracle could not detect a true positive.** Every "0 traces" reading up to that point was an artifact of the query, not a measurement of the system. Trace ids now come from the Cloud Run request log and from the API response, and are fetched by id.

**And the id being reported was the wrong trace.** The endpoint wrapped the delegation in its own root span and returned that span's trace id. The ADK runner starts its **own** root `invocation` span in its own execution context, so the delegation is one coherent trace that an outer wrapper does not adopt. Measured locally against a collecting exporter: **12 spans, 11 correlated under ADK's root and the wrapper alone in a second trace.** Cloud Trace confirmed it exactly — the returned id resolved to a single useless span. The id is now read from inside the run, by the agents themselves, so it names the trace the waterfall is actually in.

**What is now true, and checkable by anyone.** `POST /api/v1/fleet/delegation_drill` returns the `trace_id` it wrote and the `trace_exporter` that wrote it. Trace `35f6bc26c177a22e99d7d491ead3b6b1`, retrieved from Cloud Trace by id, contains **11 spans in one waterfall**:

```
invocation
   invoke_agent fleet_orchestrator
      invoke_agent licensing_negotiator
         negotiator.read_grants          identity=licensing-negotiator-sa  policy=gateway_policy_v1      outcome=PERMITTED
      registry.discover                  identity=licensing-negotiator-sa  policy=registry_role_scope_v1 outcome=NOT_DISCLOSED
      invoke_agent rights_custodian
         custodian.initiate_revocation   identity=rights-custodian-sa      policy=gateway_policy_v1      outcome=INITIATED
      registry.discover                  identity=rights-custodian-sa      policy=registry_role_scope_v1 outcome=DISCOVERED
      invoke_agent revocation_propagator
         propagator.execute_cascade      identity=revocation-propagator-sa policy=supervisor_deadline_v1 outcome=ABANDONED
      supervisor.quarantine_and_reroute  identity=revocation-propagator-sa policy=quarantine_policy_v1   outcome=QUARANTINED_AND_REROUTED
```

The conflict topology is legible in the trace itself: the buyer's negotiator asks the registry for the propagator and gets `NOT_DISCLOSED`; the artist's custodian asks and gets `DISCOVERED`.

**What is now structural.** `tests/test_trace_backend_honesty.py` asserts the exporter is pinned to an exact version, that the cloud→console fallback logs at ERROR and names what to check, that `deploy.sh` verifies **both** the API and `roles/cloudtrace.agent` before setting the flag, that a requested-but-unavailable backend is reported as its own distinct value rather than collapsing into `console`, and that the drill returns the fleet's trace id rather than one it minted. Mutation-verified against all three real defects.

**The lesson.** Four mechanisms in sequence — an env var, an exporter, a flush, an id — each reported success, and the claim was false at every step. The one that cost the most was the broken oracle, because it produced confident evidence *for* a wrong conclusion. **Before believing a negative result, check that the instrument can detect a positive one.**

---

## Named finding — the conflict boundary became a credential boundary, and it cost 1.2 seconds

**Done:** 2026-08-14 · **Requirements:** HOD-733 · **Status:** deployed, verified live, guarded

**What `in_process_only` actually meant.** For the life of this project the rights custodian, licensing negotiator, evidence agent and consent arbiter were four ROLES inside one Cloud Run process running as one service account. The policy was real, enforced at every call, and tested at three altitudes — and the process held credentials for every domain, so the boundary was a property of our code rather than of the infrastructure. `docs/deployment_status.json` said exactly that, and two external reviews named it as the gap between the architecture described and the architecture deployed.

**Five things had to be true, and only the last one is the interesting part.** Each role now runs as its own private Cloud Run service under its own service account. The live domain data moved into the per-domain databases. The gateway routes per **(role, collection)** rather than per role — routing on the role alone would have sent the shared grant log into a domain database. The front door delegates domain reads and writes over authenticated Cloud Run, and the callee **pins its role from its own environment** and refuses any request naming a different one, because a role asserted in a request body is the same defect as a `counterparty_id` asserted in a request body. And then:

**The front door's own identity was narrowed to `(default)`.** Deploying four services changes nothing while the caller can still read every database itself — the delegation would be decoration. `hodi-runtime-sa` held **unconditioned** `datastore.viewer` and an unconditioned append-only role, so it could reach all four domain databases. Both are now conditioned to `(default)`, added before the broad grants were removed so the live service was never without credentials. `tests/test_workload_identity.py` asserts the pair that matters: the front door is **refused by Google IAM** on `hodi-identity`, `hodi-commercial`, `hodi-evidence` and `hodi-adjudication`, **and still reads the `(default)` grant log**. Asserting only the refusal would pass against a completely broken service account.

**Three defects surfaced during the work, and all three were pre-existing.**

1. **`/evidence-counts` had never been authorised.** It read four collections with a RAW Firestore client — no gateway, no policy check, no denial event. Routing it through the gateway for the split revealed that the evidence agent was not permitted three of the four evidence collections it reports on. The counts had not been wrong; they had simply never been asked. The policy now grants what it always should have.
2. **A collection existed in two databases at once.** `crawler_access` moved, and four call sites in `main.py` kept reading and *appending* to `(default)`. `/evidence-counts` confidently served **3** against a corpus of **1904** — a live surface reporting a number from the database the data had just left. Nineteen records accrued there before the sweep caught them.
3. **The migration's own verification was wrong, and failed safe.** It compared the destination's whole digest against the source's, which holds only when the destination starts empty — so the incremental sweep aborted rather than deleting rows it could not prove it had copied. Correct instinct, wrong comparison: the property is that every source document is present byte for byte, not that the two sets are equal. Fixed to containment.

**What it cost, published rather than absorbed.** The revocation cascade went **~737 ms → ~1896 ms** and the permitted licence **~712 ms → ~1675 ms**. Both paths verify that the artist owns the work; that check reads `works`; `works` now lives behind the rights-custodian workload. An in-process function call became an authenticated HTTPS hop. The denial is no longer the fast path either — it pays the same hop before it can refuse, which is the right order, because you cannot decide a request about a work without first establishing the work. Cold is worse and now involves two services: **3973 ms** with the front door and the custodian both cold. Every figure is updated in `metrics.json`, the README, the recording script and `prepare_recording.py`'s prediction, because the recording script quotes them on camera.

**What did NOT change.** `make demo` is still credential-free and still passes: delegation is off unless a deployment sets `HODI_DOMAIN_SERVICE_URLS`, and `DomainServiceClient.handles()` returns False under `HODI_OFFLINE` regardless of configuration. A declared offline run must not open a socket.

**What is still application-layer, stated rather than blurred.** The append-only grant log stays in `(default)` and every domain-appropriate identity reaches it — that is the point of the system. So row-level separation *inside* `grants`, which buyer's rows a negotiator may see, remains gateway-enforced and cannot be solved by moving databases. Per-domain databases were never going to fix that, and saying they had would have been the overclaim this project exists to refuse.

**The near-miss worth recording.** The first version of `deploy_domain_services.sh` bound each domain SA a project-wide `roles/datastore.viewer` — an unconditioned read grant on **every** database, which would have silently undone the entire split while every test and every deploy step reported success. This project already failed that exact proof once, on these same service accounts. A test now fails the build if the script ever adds one.

---

## 2026-08-18 — Readiness corrections and the revocation worker's broad credential

**Crawler-log volume and Gemma triage rate.** The source remains `docs/metrics.json`: `daily_crawler_accrual_metrics` is the only rendered crawler-volume source and `gemma_triage_routing_distribution` is the only rendered routing-rate source. This entry deliberately does not duplicate their values. The current audit retains the same claim limit: non-self-originated requests are not crawler counts, and only `known_crawler_ua_matches` may be described as crawler access.

**Canary results and `spend_to_date`.** Unavailable in the current `docs/metrics.json`; reported as **unavailable**, not reconstructed from prose or replaced with a plausible value.

**Scope-lattice edge cases.** No new containment edge was discovered. The 56-case matrix remains green. The boundary edge case was IAM rather than lattice semantics: mapping the revocation domain to `(default)` does not make an unconditional project role default-only. Without a resource condition, that credential also reaches every named Firestore database.

**Google-toolchain finding.** Cloud Run workload separation is only real when three independent pieces agree: `roles/run.invoker` selects who may call the service, the callee pins its role from its own environment and verifies the caller's OIDC email, and Firestore IAM scopes the callee to its database. A private service with a project-wide viewer is still a cross-domain credential. The front-door client now also requires a literal execution-surface marker from the worker; an unrelated HTTP 200 is not accepted as proof that the propagator workload executed the cascade. No new Antigravity runtime observation was made; the recorded headless-SDK result and ADK/OTel span behavior remain unchanged.

**Deployment truth.** The code and offline tests implement the worker cutover and IAM narrowing. They have not been deployed in this session. `docs/deployment_status.json` therefore records the worker as `provisioned_unverified` and the route cutover as `scripted_not_executed`; no new live latency, trace, KMS, crawler, or IAM result is claimed.
