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
