# Hodi — Creative Consent Administration Fleet

*"Your voice is in a product you never agreed to."*

Hodi is a governed fleet of institutional agents that administers creative consent end to end: registering works with proof of control, expressing scoped machine-readable terms, negotiating with buyers under confidentiality, and propagating revocations across affected grants. The fleet's four agents are separated by conflict of interest — not by task — and every inter-agent call passes a policy-enforcing gateway whose denials are logged as structured events, never silent. Hodi's audit record refuses to assert anything it cannot verify, structurally: the schema itself cannot express the claims the system will not make.

**Hodi is the knock.**

---

## The honesty invariants — enforced by structure, not prose

This table is lifted verbatim from the PRD (§3.4). Every enforcement mechanism is checkable in this repo.

| Invariant | Enforcement mechanism (checkable in this repo) |
|---|---|
| No agent can read another buyer's terms | Per-agent service accounts + gateway policy; the negotiator's SA is scoped to one `counterparty_id` per session. Negative-test matrix asserts `PERMISSION_DENIED` on cross-buyer reads. |
| No verdict about training-set membership can exist | The `class` enum has no such value; the schema cannot express it. Every `EvidenceRecord` carries a literal `claim_limit` string. A render-time lint rejects the phrases "trained on", "was in the training set", "proves training" in any generated text. |
| Evidence classes never aggregate | No numeric field on `EvidenceRecord`; no summing, scoring, or ordering across classes anywhere; the renderer groups by class and refuses a total. |
| Grants are never mutated | Append-only `create()`-only event log with deterministic IDs; revocation is a **new event that supersedes**; the original grant remains visible with a strikethrough, never deleted. |
| Current state is always a fold | `resolve(grant_id, at=t)` is the single read path; "what was permitted on March 3" is the same fold, dated. |
| Ownership is verified or explicitly not | `control_tier` is mandatory; `verified_control` requires a stored `control_proof`; the UI renders the three tiers differently and never hides `asserted`. |
| Untrusted documents cannot redirect the fleet | Prompt Inspector (local regex) on post-extraction bytes of every inbound buyer/scope document; detection emits an event and an anomaly item and the request **proceeds** under its original scope. |
| A looping or hallucinating worker cannot stall the fleet | Supervisor with per-agent deadline and circuit breaker; quarantine + reroute; `TaskAbandoned` events; every decision carries an OTel span. |
| Least privilege | One SA per agent, per the conflict boundaries below; no SA holds two of {identity, buyer terms, evidence, revocation}. |

---

## Why four agents: the conflict-of-interest topology

The separation is a **conflict of interest**, not a division of labour:

- The **rights custodian** holds artist identity and must see it.
- The **licensing negotiator** talks to buyers and must **not** see other buyers' negotiated terms — rate confidentiality is the norm and a leak destroys the next deal. Its service account is scoped to one `counterparty_id` per session.
- The **evidence agent** reads access logs and outputs and must **not** see commercial terms, or its findings become interested.
- The **revocation propagator** acts across grants and must not hold identity.

A single agent would need the union of all four permission sets — precisely the position no honest broker may occupy. **A monolith here would itself be the violation.**

The full permission matrix is in [docs/architecture/conflict_matrix.md](docs/architecture/conflict_matrix.md). That document is **GENERATED** from [src/schema/iam_policy.py](src/schema/iam_policy.py) by [scripts/generate_conflict_matrix.py](scripts/generate_conflict_matrix.py), so the documentation cannot drift from the enforced bindings — the doc and the gateway consult the same data.

---

## Quickstart

```bash
pip install -r src/evidence_service/requirements.lock
make demo
```

**Zero credentials, no network, no emulator.** Verified from a clean clone of this repository in a fresh `python:3.11-slim` container with no mounted config. Runs entirely from committed fixtures and proves, with assertions that fail the run if false: the scope-lattice partial order (declared as data); byte-stable replay of `resolve()` over a shuffled event log; revocation narrowing the present without rewriting the past; the poisoned buyer document detected and proceeding under its original scope with an identical licensable outcome; all four conflict walls denying forbidden reads with structured `PolicyDenialEvent`s; and the schema refusing to express training-set membership.

```bash
make demo-live
```

Runs the three-call boundary test against the **deployed** Cloud Run service: a properly scoped read that succeeds with real grant documents, an unfiltered read that is denied, and a cross-counterparty read that is denied — each denial returned and logged as the same structured event. Public endpoint, no credentials; wall-clock time is printed (about 1 second warm).

```bash
make verify-scopes
```

Prints the lattice table from its declaration as data and runs the 45-case containment truth table across all five gating dimensions simultaneously (use-type, model class, commercial status, territory, temporal validity), including empty-territory semantics and union-across-grants cases.

```bash
make verify-manifest
```

Fetches the **live** `/works` manifest and verifies the corpus-integrity properties: the 5-work registered corpus is served, every `verified_control` work has a stored proof whose URI resolves with HTTP 200, and every work carries its canary string and plant date.

```bash
make compliance
```

Extracts every requirement ID from the PRD and diffs §4 against the §2 compliance matrix **and the prose**; fails on any orphan or range notation. Verifies 54 requirements as of this writing.

---

## Reproducing the demo, beat by beat

| On-camera moment | Command |
|---|---|
| The author's registered works, terms attached, control tiers rendered distinctly | `curl https://hodi-evidence-endpoint-406699565497.us-central1.run.app/works` (or `make verify-manifest`) |
| Machine-readable consent terms at a well-known URI | `curl https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json` |
| The four conflict walls denying forbidden reads, with structured denial events | `make demo` (Beat 5, in-process) and `make demo-live` (deployed path) |
| Live buyer scope request; Prompt Inspector catches the poisoned document; request proceeds under original scope | `make demo` (Beat 4, fixture path) — live path: `POST /api/v1/license` with [fixtures/buyer_request_poisoned.json](fixtures/buyer_request_poisoned.json) |
| Revocation narrows the present, never the past; all events remain visible | `make demo` (Beat 3) — live cascade: `POST /api/v1/revoke` |
| OTel span per agent decision, carrying agent identity, policy consulted, outcome | `python3 src/harness/main.py` (prints span payloads; exits 1 by design, recording the HOD-020 result) |
| The honesty beat: what Hodi will not say | `make demo` (Beat 6) and Diagram B in [docs/architecture/](docs/architecture/) |

---

## What Hodi will not claim

- **Training-set membership is not determinable, and Hodi cannot say it.** Membership inference against frontier models is an unsolved problem. The `EvidenceRecord.class` enum has no such value — the schema cannot express the claim — and every record carries the literal `"This record does not assert training-set membership."` A render-time lint rejects the claim in generated text, including paraphrases.
- **Revocation terminates a grant. It does not un-train a model.** Revocation is a legal instrument with technical enforcement of the grant, a dated signed notice, and a receipt. A lint asserts that no generated notice implies removal from a model.
- **`crawler_access` is designed and instrumented, but third-party accrual has not yet been observed.** The evidence endpoint has logged every access since Aug 6, 2026. As of the Aug 7, 2026 audit ([docs/metrics.json](docs/metrics.json)): 160 accrued records, **zero attributable to third parties** — 159 are the project's own instrumented tooling, and the single browser-user-agent record originates from the developer's own IP via the corpus audit script. The endpoint continues to accrue through judging; if third-party accrual is still zero at recording time, that negative result is stated on camera. *"I published machine-readable consent terms at a discoverable endpoint and nobody asked"* is itself an instrumented finding about current scraper etiquette.
- **`verbatim_match` is designed but not demonstrated.** It is the one evidence class requiring an external model surface, whose outputs cannot be guaranteed or forced during a demonstration. The class exists in the schema and the checking code exists; no live hit is claimed.

Stated plainly, without apology: these are the limits of what is checkable, and the product's value is that it stops exactly there.

---

## Negative decisions

- **No vector database.** Every query the registry answers is an exact fold over typed events — `resolve(grant_id, at=t)`, filtered reads by `counterparty_id`. Similarity search would exist only to rank or aggregate evidence across classes, which the invariant table forbids. It would be infrastructure for a query the schema refuses to answer.
- **No O(n²) verbatim sweep.** Comparing every crawled page against every registered work is N×M. At the real corpus's scale today (5 works × 160 logged accesses) that is at most 800 comparisons — and at any real registry scale (10⁵ works × 10⁷ pages) it is 10¹² and dead on arrival. Evidence is event-driven instead: planted canaries, access logs, and targeted checks.
- **No second front-end.** The buyer surface is a signed API with machine-readable license documents and receipts. Two UIs is how a 26-day build becomes a 40-day build.
- **No takedown automation, no litigation tooling, no enforcement actions.** Hodi is a licensing rail, not a weapon.

---

## Technologies used

Build history and daily findings are first-class artifacts here, including the corrections:
**[docs/BUILD-LOG.md](docs/BUILD-LOG.md)** — every session's verbatim prompt, outcome, and forked decisions, including dated correction notes where earlier entries overclaimed and were struck.
**[docs/FINDINGS.md](docs/FINDINGS.md)** — daily observations: crawler-log audits, scope-lattice edge cases, and the Google-toolchain findings, including the Antigravity headless/OTel result below.

- **ADK (Google Agent Development Kit) + OpenTelemetry** — the runtime agent framework: four role-separated agent classes under four distinct service accounts, every agent decision exporting a span carrying `agent.identity`, `policy.consulted`, and `outcome`. Chosen by the pre-committed branch documented in [docs/antigravity/decision.md](docs/antigravity/decision.md).
- **Gemini via Vertex AI** — the fleet's model tier (HOD-301: pinned model ID literals, temperature 0, shared response cache). Honest status, per [docs/FINDINGS.md](docs/FINDINGS.md): as of the Aug 7, 2026 probe, this project reaches Gemini 2.5-generation models on Vertex (observed HTTP 200 from `gemini-2.5-flash`); Gemini 3.5-generation model IDs returned 404 in both `us-central1` and `global`. Model IDs are pinned as exact literals, never rolling aliases.
- **Gemma (local, via Ollama)** — first-pass triage of crawler access records (bot / human / unknown) before anything reaches Gemini. Deliberately non-load-bearing: if Gemma inference is offline, a heuristic fallback classifies, and evidence records are still produced.
- **Firestore** — the append-only grant-event log. Deterministic event IDs, `create()`-only discipline, custom IAM role withholding `update`/`delete` from every agent SA. State is always a fold over events.
- **Cloud Run** — the deployed evidence endpoint and buyer API (services), and the headless verification harness (jobs). `min-instances=0`, max capped.
- **Cloud Logging** — gateway policy denials land as structured `jsonPayload` events (severity WARNING), queryable by calling SA, collection, and policy — the same event object the API returns.

---

## Building on the Antigravity SDK

The Antigravity SDK was verified against a pre-committed boolean assertion, quoted here from [docs/antigravity/decision.md](docs/antigravity/decision.md):

> *From a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying (a) the invoking agent's identity, (b) the policy consulted, and (c) the outcome.*

**Observed result (verbatim in the decision document):** the headless Cloud Run Job `hodi-antigravity-harness-2l2ql`, running under distinct SAs (`agent-delegator@…`, `agent-worker@…`), failed the assertion at the first check: `No module named 'google.antigravity'`. Antigravity does not currently expose a headless server-side Python surface for multi-agent delegation under distinct GCP service accounts. Partial emission had been pre-committed as a fail, so the branch executed the same day: runtime agent execution moved to **ADK + the OpenTelemetry SDK**, whose spans carry all three required attributes (full span payloads are in the decision document).

This is a finding about the SDK's current headless surface, published rather than buried: a negative result with the exact harness, error text, and span payloads a toolchain owner would need to reproduce it.

---

## Provenance

- **First commit:** `76392260f65c4e253d82db530a36d456cc0768ce` at `2026-08-06T12:37:20-05:00` (`2026-08-06T17:37:20Z`).
- **Public, unsquashed history** at [github.com/Jeremiah-Sakuda/Hodi](https://github.com/Jeremiah-Sakuda/Hodi) from the first commit onward. All code was authored inside the submission period.
- **Relationship to my other submissions:** this project shares an append-only claim-record/event-log lineage with the author's other hackathon submissions. The axes of difference are the user (artist-side principals), the data (this project's corpus is the author's own published work — real essays, repos, and bass recordings, never synthetic), the governance regime (consent and licensing), and the agent topology (four agents separated by conflict of interest).

---

## Security & data integrity

- **Prompt inspection is local, and labelled as such.** The managed Model Armor guardrail could not be used: the API is in restricted preview and template creation returned HTTP 403 for this project. The claim was pulled rather than shipped under a Google product's name. Prompt inspection is implemented as a local regex and is labelled `local_regex_inspector` everywhere it appears — in code, in API responses, and in the evidence counts endpoint.
- **The security posture rests on IAM boundaries, gateway policy enforcement, and audit traces.** Four service accounts, no SA holding two conflict domains, a custom Firestore role that cannot update or delete grant events, and a gateway that converts every policy violation into a structured, logged `PolicyDenialEvent`.
- **`/api/v1/debug/compromised_agent_read` is a public endpoint on purpose.** It simulates a compromised licensing negotiator attempting three reads: one properly scoped to its own session counterparty (which succeeds, returning that counterparty's grants — data the negotiator is entitled to), one unfiltered, and one cross-counterparty. The last two are structurally guaranteed denials: the gateway consults the same policy data as production traffic, so the endpoint can only produce denial events plus the one read the caller was always allowed. It exists so a reviewer can verify the cross-buyer confidentiality boundary over the public network in under a minute, without credentials. Run it: `make demo-live`.

---

## Live services

- Evidence endpoint: `https://hodi-evidence-endpoint-406699565497.us-central1.run.app`
- Consent terms: [`/.well-known/hodi.json`](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json)
- Registered works manifest: [`/works`](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/works)
- Canaries index: [`/canaries`](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/canaries)
- Evidence counts by class (no totals, by design): [`/evidence-counts`](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/evidence-counts)

Deployed-path timings (measurement surface: `deployed-over-network`, from [docs/metrics.json](docs/metrics.json)): buyer API 896 ms cold / 560 ms warm average; revocation cascade 467 ms cold / 287 ms warm average; supervisor deadline 5.0 s, derived from an observed p95 of 2939 ms with 1.7× headroom.
