# Hodi — Product Requirements Document

**Version:** 1.2 · **Date:** Aug 5, 2026 (v1.2 amendment Aug 14, 2026) · **Owner:** Jeremiah Sakuda
**Entity:** Individual entry · **Hackathon:** All Things Agentic (deadline Aug 31, 7:00 PM CDT = **Sep 1, 00:00 UTC**)
**Category:** The Fortified Enterprise Fleet · **Category fit:** see §9.
**Name:** *Hodi* — what you call at someone's door before entering. The Swahili answer to "you knock first."
**Opening line:** *"Your voice is in a product you never agreed to."* · **Thesis line:** *"Hodi is the knock."*

**Changelog v1.0 → v1.1** — all fixes, no new scope.
| # | Change | Reason |
|---|---|---|
| 1 | **Aug 14 checkpoint gets a number** (HOD-006) | A checkpoint without a pass bar is a date you talk yourself past — and Phase 2 is the densest stretch in the portfolio. |
| 2 | **Aug 8 Antigravity decision is a boolean assertion** (HOD-020) | "Unavailable" is a clean branch; "emits spans but without agent identity" is not. Aug 8 is not a day for deliberation. |
| 3 | **Scope lattice split into three requirements** (HOD-104, HOD-106, HOD-107) | Containment across use-type, territory, commercial, and temporal validity is the actual product; one AC under-specified it. |
| 4 | **Supervisor split** (HOD-341 deadline/breaker, HOD-342 quarantine/reroute) | Four or five mechanisms in one requirement, answering the track's failure-tolerance language and appearing on camera. |
| 5 | **Wall-clock measured 3× on the deployed path** (HOD-317) | Two live beats whose duration was an assumption; you get one take. |
| 6 | **Seconds-denominated video cut order** (§6) | The build cut list cannot recover video runtime on Aug 27. Eight proofs in 3:40 needs its own ladder. |
| 7 | `verbatim_match` fallback stated (HOD-320) | The one evidence class needing an external model surface. |
| 8 | Portfolio positioning noted (§9) | Recorded outside this repository. |

**Changelog v1.1 → v1.2 (Aug 14, 2026)** — an external judge-style review was implemented in full by explicit owner decision; the banked-PRD and feature-freeze overrides are recorded in `docs/GATE.md` §4. All additions; no existing requirement weakened; invariants and non-goals untouched.
| # | Change | Reason |
|---|---|---|
| 1 | **Authorization tuple gains the resource** (HOD-701) | A buyer's training grant for Work A must not imply training rights for Work B. Grants were matched by counterparty alone — the review's top correctness finding, and the repo's own recorded open item. |
| 2 | **Temporal containment is a lattice dimension** (HOD-702) | A grant valid through September cannot authorize a request through December just because it is evaluated in August. `requested ⊆ granted` must include time. |
| 3 | **Assertion authority + Consent Arbiter** (HOD-703, HOD-704, HOD-705) | Zero trust applied to epistemic authority, not just data access: what an agent may *claim* is policy, enforced at the gateway. The arbiter concludes only what typed assertions support — `ACCESS_OUTSIDE_DECLARED_POLICY` can be established while `MODEL_TRAINING` remains structurally inexpressible. |
| 4 | **Cryptographic provenance** (HOD-706) | The `UNSIGNED_PLACEHOLDER` honesty stands until real asymmetric signing exists; this builds it (Cloud KMS live, labelled ephemeral key offline) with an independent verifier, instead of HMAC theater. |
| 5 | **Execution leases** (HOD-707) | Python cannot kill a thread; quarantine meant "no new work", not "no late writes". A lease checked immediately before every side-effecting write turns quarantine into a safety property. |
| 6 | **Revocation idempotency + outbox** (HOD-708) | Notice write and grant-event write are separate effects; a crash between them plus a retry must not double-notify. Exactly-once business effect over at-least-once execution. |
| 7 | **Registry and Memory Bank made durable** (HOD-709, HOD-710) | Both claims were stronger than the process-local mechanisms behind them. Publications and memory now fold over a persistent store. |
| 8 | **Workload identity made real** (HOD-711) | Conflict boundaries move from "our program promises" to "this workload literally lacks credentials": per-domain named Firestore databases with per-SA IAM, and the revocation worker split out as its own service identity. |
| 9 | **Red-team drill** (HOD-712) | The demo proves boundaries under attack, in one command, rather than narrating happy paths. |
| 10 | **Constrained negotiation** (HOD-713) | Gemini negotiates language; the lattice caps authority. Scope terms only — the no-payments non-goal stands. |
| 11 | **Durable trace export** (HOD-714) | Console-exported spans are instrumentation, not an observability story; the delegation must be reconstructable from a backend. |

**Changelog, second pass (Aug 14, 2026)** — a second external review of the v1.2 build. Every one of its findings was verified against the code before being acted on; two were **worse than reported** and are noted as such.
| # | Change | Reason |
|---|---|---|
| 12 | **Deployment claims derived from evidence** (HOD-715) | The README asserted asymmetric signing "has not been built" for a commit *after* it was built. Prose is the wrong home for a deployment claim; it now derives from `deployment_status.json` under a bidirectional guard. |
| 13 | **Storage fails closed** (HOD-716) | *Worse than reported.* A credential failure did not merely risk process-local data — it silently turned every read into "no documents exist" and every write into a dying buffer, both answering HTTP 200. A licensing decision over phantom state that looks healthy. |
| 14 | **Caller identity bound and verifiable** (HOD-717) | *Worse than reported.* The review assumed role and service account were "checked for consistency"; nothing checked them at all — `calling_sa` was logging-only. Enforcing the binding then surfaced two production paths using service accounts the policy does not declare. |
| 15 | **Registration is a running operation** (HOD-718) | `/works` was a Python literal, so "register your work" needed a redeploy — a claim the running system could not honour. |
| 16 | **A counterparty that stops** (HOD-719) | Hodi terminating a grant in its own log is administration. A second system halting because the rail told it to is the product, and nothing demonstrated it. |
| 17 | **Live release verification** (HOD-720) | A green badge proved the credential-free simulation, not the deployed path. Now a WIF-authenticated run proves the deployed path *and writes its own result* into the deployment claims. |

---

## 1. Product definition

### 1.1 The problem
Consent for creative work has no infrastructure. An illustrator cannot say *"this series may be trained on, that one may not, and this third may for a fee with attribution"* in any form a counterparty can read, verify, or be held to. The available options are a checkbox on a platform you don't control, a `robots.txt` line covering a whole domain, or a lawsuit years later. Meanwhile a buyer acting in good faith has no way to find work that is actually licensable, so acquisition happens by scraping and gets resolved by litigation.

Both sides are stuck for the same reason: **there is no machine-readable, verifiable, revocable expression of creative consent, and no auditable record of who agreed to what, when, under which terms.**

### 1.2 What Hodi is
A governed fleet of institutional agents that administers creative consent end to end: registering works with proof of control, expressing scoped terms, negotiating with buyers under confidentiality, propagating revocations across affected grants, and maintaining an audit record that never overclaims.

**The knock:** a buyer submits a scope request; the fleet answers with a licensable set, terms attached, exclusions explained, and a signed receipt. Nobody takes anything without asking.

### 1.3 Honesty invariants — the product's spine, and non-negotiable
Hodi's credibility rests entirely on refusing to assert what it cannot verify. Three rules, enforced structurally (§3.4), not by prose:

1. **Hodi never claims a work was in a training set.** Membership inference against frontier models is unsolved; a system that claims otherwise is lying. Hodi reports only what is checkable, in typed evidence classes that cannot be aggregated into a score (§3.3).
2. **Revocation terminates a grant. It does not un-train a model.** Revocation is a legal instrument with technical enforcement of the *grant* and a dated, signed notification with a receipt. Any copy that implies removal from a model is struck.
3. **Ownership is verified or explicitly not.** A registration carries `control_tier: verified_control | asserted | disputed`, rendered differently everywhere it appears. A system that confidently attributes rights to whoever typed first is worse than no system.

### 1.4 Non-goals (README negative decisions)
- **No training-set membership detection.** Stated as a designed limit with the reason, not omitted.
- **No adversarial perturbation** (Glaze/Nightshade-style). That is protection, not consent, and it is an arms race against more compute.
- **No takedown automation, no litigation tooling, no enforcement actions.** Hodi is a licensing rail, not a weapon.
- **No named real-world adversary, ever.** Every fixture scraper is fictional and unnamed. No real company appears as a violator in the repo, the video, the blog, or any social post. This is a hard rule (§5).
- No payments, no escrow, no marketplace UI. The buyer surface is an **API with signed requests and receipts**, never a second front-end — two UIs is how this becomes a 40-day build.
- No PMF argument anywhere. This is not a startup pitch; Startup Excellence is a different submission's lane.

---

## 2. Hackathon compliance matrix

Cells enumerate IDs. `make compliance` (HOD-007) diffs §4 against this table **and against the prose**.

| Rule requirement | How Hodi satisfies it | Req IDs |
|---|---|---|
| Gemini 3.5+ via Vertex AI | Gemini 3.5 Flash (natural-language scope interpretation in the buyer API — the model interprets intent, the lattice decides permission; revocation notice drafting gated by lint) for scope interpretation and notice drafting; log triage is Gemma's tier, not a second Gemini. Pinned model ID literals on the `global` endpoint. *Corrected 2026-08-07: `gemini-3.5-pro` does not exist in the Vertex publisher catalog for this project — availability probed empirically, see FINDINGS.* | HOD-301 |
| ≥1 Google Agent Framework | **Antigravity SDK** (four agents + supervisor); **ADK dual-listed as the fallback**, decided Aug 8 | HOD-020, HOD-302 |
| ≥1 Google Cloud infra service | Cloud Run services + Jobs, Firestore, Cloud Scheduler, Cloud Logging/Trace | HOD-005, HOD-410 |
| New project in Submission Period | Public remote from first commit, unsquashed; pre-Aug-3 audit; **`## Relationship to my other submissions`** disclosing the shared claim-record lineage by path and date | HOD-001, HOD-002, HOD-004, HOD-006 |
| Category | The Fortified Enterprise Fleet | — |
| **Fleet: cataloged for cross-department use** | **Agent Registry** — agents published with versions, scopes, and owning function; discoverable and invocable by role; publications, heartbeats and deregistrations fold over a durable store | HOD-310, HOD-330, HOD-709 |
| **Fleet: context across weeks of async operation** | **Memory Bank** — grants, scopes, and revocations are long-lived state with temporal validity; the registry survives instance death; crawler logs accumulate for weeks; the memory-bank class itself reads through the persistent store | HOD-101, HOD-102, HOD-103, HOD-320, HOD-331, HOD-710 |
| **Fleet: production data without violating policy** | **Agent Identity** (per-agent scoped SAs; role bound to service account on every call, OIDC-verified where deployed; per-domain named databases so a workload literally lacks foreign-domain credentials), **Agent Gateway** (routing + policy enforcement at the boundary; work-scoped, window-contained authorization; assertion authority; storage fails closed), **Prompt Inspector** (deterministic first-pass injection indicator on untrusted buyer documents) | HOD-102, HOD-311, HOD-312, HOD-313, HOD-340, HOD-701, HOD-702, HOD-703, HOD-711, HOD-716, HOD-717 |
| **Fleet: audit reasoning** | **Agent Observability** — OpenTelemetry traces end-to-end; every agent decision carries a span; durable trace backend; signed, independently verifiable incident manifests; deployment claims derived from verification runs | HOD-340, HOD-706, HOD-714, HOD-715, HOD-720 |
| **Nexus: failure tolerance** | Supervisor quarantine + reroute on loop, timeout, or scope violation; per-agent circuit breaker; `TaskAbandoned` on deadline; execution leases deny a woken worker's late writes; idempotent revocation with a notice outbox; the five-attack red-team drill | HOD-341, HOD-342, HOD-350, HOD-707, HOD-708, HOD-712 |
| Devpost — features/functionality | `docs/devpost-description.md` §1; autonomous consent incident response (arbiter, containment, signed manifest); constrained buyer↔Hodi negotiation; artist work registration; a buyer-side client that honours revocation | HOD-104, HOD-105, HOD-106, HOD-107, HOD-622, HOD-704, HOD-705, HOD-713, HOD-718, HOD-719 |
| Devpost — technologies used | `docs/devpost-description.md` §2 (Gemma named) | HOD-622, HOD-623 |
| Devpost — other data sources | `docs/devpost-description.md` §3 — **the corpus is the author's own published work** | HOD-009, HOD-622 |
| **Devpost — findings and learnings** | `docs/devpost-description.md` §4, **drafted Aug 12–13**, `{{fill from metrics.json}}` slot | HOD-317, HOD-509, HOD-622 |
| ≤4-min video, public YouTube | §6 shot list; target 3:40, hard cap 4:00 | HOD-601, HOD-602, HOD-603, HOD-604, HOD-605, HOD-606, HOD-607, HOD-608 |
| Repo + spin-up | `make demo` credential-free; emulator path; bootstrap/teardown | HOD-501, HOD-506 |
| Architecture diagram | Two diagrams; every number traces to `/docs/metrics.json` | HOD-505 |
| Hosted project | Public registry + `/.well-known/hodi.json` + signed buyer API + evidence endpoint + artist console; `min-instances=0`, max capped | HOD-008, HOD-360, HOD-370, HOD-411 |
| Bonus: blog | Drafted Aug 12–13, published Aug 28, created-for-hackathon language | HOD-621 |
| Bonus: social | Aug 20 teaser + Aug 30 launch, hashtag exact, **naming Hodi** | HOD-620, HOD-624 |
| Bonus: additional Google model | Gemma as the crawler-log triage tier — README + diagram + ≥1s video | HOD-303, HOD-623 |
| **Build-toolchain evidence is reachable** | README `## Technologies used` links `docs/BUILD-LOG.md` and `docs/antigravity/decision.md`; Antigravity labelled on Diagram A; blog leads its second half with the Antigravity multi-agent + OTel findings | HOD-010, HOD-505, HOD-510, HOD-621 |

**Bonus ceiling is +0.6.** No Veo, no Lyria — bolting either onto a rights registry is transparent point-farming and it retroactively cheapens the honest Gemma integration.

---

## 3. System architecture

### 3.1 The fleet
```
                        AGENT REGISTRY  (publish · version · discover · scope)
                                │  every agent below is registered, versioned, role-scoped
                                ▼
   ┌──────────────── AGENT GATEWAY (routing + policy enforcement) ────────────────┐
   │  every inter-agent call passes here · policy denials are logged, never silent │
   └───┬───────────────┬────────────────────┬─────────────────────┬───────────────┘
       ▼               ▼                    ▼                     ▼
  RIGHTS           LICENSING            EVIDENCE             REVOCATION
  CUSTODIAN        NEGOTIATOR           AGENT                PROPAGATOR
  artist identity  buyer-facing         crawler logs,        computes affected
  works, terms     ONE buyer at a time  canaries, verbatim   grants, emits signed
  control tier     never sees others'   NEVER claims         notices + receipts
                   terms (IAM-enforced) training membership
       │               │                    │                     │
       └───────────────┴────────┬───────────┴─────────────────────┘
                                ▼
                  append-only grant-event log (Firestore)
                  grants · scopes · revocations · receipts
                  state = fold; "what was permitted on March 3" is the same fold, dated
                                │
        ┌───────────────────────┴────────────────────────┐
        ▼                                                ▼
  SUPERVISOR                                    BUYER API (signed requests)
  quarantine · reroute · circuit-break          /.well-known/hodi.json
  OTel traces for every decision                scope request → licensable set + receipt

  PROMPT INSPECTOR sits on every untrusted inbound document, post-extraction
```

### 3.2 Why this is structurally multi-agent
The separation is a **conflict of interest**, not a division of labour:
- The rights custodian holds artist identity and must see it.
- The licensing negotiator talks to buyers and must **not** see other buyers' negotiated terms — rate confidentiality is the norm and a leak destroys the next deal.
- The evidence agent reads access logs and outputs and must **not** see commercial terms, or its findings become interested.
- The revocation propagator acts across grants and must not hold identity.

A single agent would need the union of all four permission sets — precisely the position no honest broker may occupy. **A monolith here would itself be the violation.**

### 3.3 Data model
```
Work { work_id, artist_id, medium, uri, content_hash,
       control_tier: "verified_control" | "asserted" | "disputed",
       control_proof: { method: "dns" | "well_known_file" | "signed_commit" | "platform_oauth",
                        verified_at, evidence_uri } | null }

Scope { use_type,        // training | fine_tuning | rag_retrieval | human_reference | synthesis
        model_class, commercial, attribution_required, territory,
        valid_from, valid_until }
// Scopes form a LATTICE with containment: a training grant contains fine_tuning;
// human_reference contains nothing. "May I fine-tune?" resolves by containment, not string match.

GrantEvent { event_id,              // deterministic: hash(grant_id, step, attempt)
             grant_id, work_id, counterparty_id, scope: Scope,
             kind: "granted" | "revoked" | "expired" | "superseded",
             supersedes: grant_id | null, issued_at, signature }

Receipt { receipt_id, grant_id, counterparty_id, payload_hash, issued_at, signature }

EvidenceRecord {
  evidence_id, work_id,
  class: "crawler_access"        // checkable: our logs, high confidence
       | "canary_hit"            // checkable: planted string returned, high confidence
       | "verbatim_match"        // checkable: near-exact reproduction, medium confidence
       | "redistribution",       // checkable: copy found at another URI, medium confidence
  observed_at, source_uri, detail,
  claim_limit: "This record does not assert training-set membership."   // literal, on every record
}
// NO training_membership class exists. NO numeric score. NO field aggregates
// across classes — that is how honest tiers collapse into a dishonest number.
```

### 3.4 Invariant table — **lift verbatim into README and Devpost**

| Invariant | Enforcement mechanism (checkable in this repo) |
|---|---|
| No agent can read another buyer's terms | Per-agent service accounts + gateway policy; the negotiator's SA is scoped to one `counterparty_id` per session. Negative-test matrix asserts `PERMISSION_DENIED` on cross-buyer reads. |
| No verdict about training-set membership can exist | The `class` enum has no such value; the schema cannot express it. Every `EvidenceRecord` carries a literal `claim_limit` string. A render-time lint rejects the phrases "trained on", "was in the training set", "proves training" in any generated text. |
| Evidence classes never aggregate | No numeric field on `EvidenceRecord`; no summing, scoring, or ordering across classes anywhere; the renderer groups by class and refuses a total. |
| Grants are never mutated | Append-only `create()`-only event log with deterministic IDs; revocation is a **new event that supersedes**; the original grant remains visible with a strikethrough, never deleted. |
| Current state is always a fold | `resolve(grant_id, at=t)` is the single read path; "what was permitted on March 3" is the same function with a timestamp. |
| Ownership is verified or explicitly not | `control_tier` is mandatory; `verified_control` requires a stored `control_proof`; the UI renders the three tiers differently and never hides `asserted`. |
| Untrusted documents cannot redirect the fleet | Prompt Inspector (local regex) on post-extraction bytes of every inbound buyer/scope document; detection emits an event and an anomaly item and the request **proceeds** under its original scope. |
| A looping or hallucinating worker cannot stall the fleet | Supervisor with per-agent deadline and circuit breaker; quarantine + reroute; `TaskAbandoned` events; every decision carries an OTel span. |
| Least privilege | One SA per agent, per §3.2's conflict boundaries; no SA holds two of {identity, buyer terms, evidence, revocation}. |

---

## 4. Phased requirements

Every AC names **the property it proves**, not the artifact it inspects. Before accepting any AC: *could this go green with the property false?*

### Phase 0 — Foundations (Aug 5–6)
- **HOD-001** Public GitHub remote from the first commit, unsquashed; first-commit SHA + ISO timestamp in the README. *AC:* public history shows continuous authorship from ≥ Aug 3.
- **HOD-002** `gitleaks` pre-commit hook; `.gitignore` SA patterns; `.env.example`.
- **HOD-004** Pre-Aug-3 audit + **`## Relationship to my other submissions`**: inventory the shared claim-record/event-log lineage by path with copy dates, and a table of the axes of difference (user, data, regime, agent topology). Do **not** use a web-framework analogy — it invites the comparison it means to deflect. *AC:* Phase 0 exit criterion, committed.
- **HOD-005** Budget alerts at **$25/$50/$100/$140**; an unconditional 23:00 UTC nightly teardown job fencing the Gemma project. *AC:* teardown on a nonexistent endpoint is a verified no-op. *Corrected 2026-08-07: Gemma now runs serverless on Vertex (per-token, `gemma-4-26b-a4b-it-maas`), so no separate capped GPU project is required; the fenced-project/$20-cap design is superseded. The nightly teardown job remains scheduled (Cloud Scheduler → Cloud Run Job) and its no-op paths are empirically verified. The budget alerts and teardown scheduling were reported complete in Phase 0 but did not exist until 2026-08-07 — see BUILD-LOG correction.*
- **HOD-006** `/docs/GATE.md` with three dated decisions and their pre-committed consequences:
  - **Aug 8 — Antigravity boolean** (HOD-020). Executed, not debated.
  - **Aug 14 — checkpoint with a pass bar:** *if fewer than 6 of HOD-301, 310, 311, 312, 313, 320, 330, 331 have passed their ACs by end of day, invoke the §7 abort ladder that day.* Aug 14 is the last day cuts are cheap; every item on the ladder is a feature or a bonus, never documentation.
  - **Aug 22 — recording-ready gate.** Question: *can I record the video from what exists on my machine today?* Feature freeze at 23:59 regardless of the answer.
  Plus a "banked" list of artifacts finished and never reopened. Deadline recorded in **UTC**.
- **HOD-007** `make compliance`. *AC:* fails on a removed ID or a range notation.
- **HOD-008** **⚠️ DAY ONE, HIGHEST PRIORITY: deploy the evidence endpoint.** A Cloud Run service serving the author's registered works with access logging to Firestore, plus `/.well-known/hodi.json` and a `robots.txt` declaring Hodi terms. **This must be live Aug 6 or the crawler-log evidence class has no real data by recording week.** *AC (property: evidence is real, not fixtured):* by Aug 26 the log contains ≥3 weeks of genuine third-party access records.
- **HOD-009** Register the author's own corpus: Medium essays, public repos, bass recordings. **Real work, real ownership, no synthetic corpus.** Plant canary strings in newly published items. *AC:* every registered work resolves to a URI the author demonstrably controls.
- **HOD-010** Build toolchain + `/docs/BUILD-LOG.md` opened (§8).
- **HOD-020** **Antigravity verification, decided Aug 8 as a boolean — not a judgment call.** The assertion that must pass, in full: *from a headless Cloud Run Job, with no interactive session, the SDK executes a two-agent delegation under distinct service accounts and emits an OpenTelemetry span per agent decision carrying (a) the invoking agent's identity, (b) the policy consulted, and (c) the outcome.* Partial emission is a **fail**, not a discussion — spans without agent identity cannot support HOD-340, and HOD-340 is the track's observability requirement. **Fail → ADK**, whose tracing story is the safer one; compliance is unaffected since ADK independently qualifies. *AC:* `/docs/antigravity/decision.md` records the assertion, the observed result verbatim, and the branch taken — a decision, not notes.

### Phase 1 — Spine and scope lattice (Aug 7–9)
- **HOD-101** Schemas per §3.3 as typed models. *AC:* an `EvidenceRecord` with a numeric field fails validation; a `Work` with `verified_control` and no `control_proof` fails validation.
- **HOD-102** Append-only grant-event log: deterministic IDs, `create()`-only, **custom IAM role** (`datastore.entities.create` + `get`, no `update`/`delete`) for every agent SA. Firestore rules govern the artist's browser path only. *AC (property: no agent can rewrite history):* a deployed agent SA receives `PERMISSION_DENIED` on an update to an existing event.
- **HOD-103** `resolve(grant_id, at=t)` as a pure fold, the sole read path for grant state. *AC:* replay over a **shuffled** fixture log, with **no emulator and no credentials** in the environment, is byte-stable.
- **HOD-104** **Scope lattice — structure.** Use-type partial order (`training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference`; `human_reference` contains no lower use-type but is contained by all of them; `synthesis` incomparable to all of the above), declared as data in `src/schema/lattice.py`, not as branching logic. *AC (property: the order is a checkable artifact, not scattered conditionals):* the relation is exported as a table and `make verify-scopes` prints it.
- **HOD-105** **Ownership verification**: DNS TXT, well-known file, signed commit, platform OAuth. *AC:* a registration without completed proof cannot reach `verified_control` by any code path.
- **HOD-106** **Scope lattice — containment resolution.** `permits(grant_scopes, requested_scope) -> bool` resolving across **all five dimensions simultaneously**: use-type containment, model class, commercial status, territory, and temporal validity. Multiple active grants resolve to the union of permitted requests via per-grant containment across all dimensions simultaneously (never per-dimension merging across grants). *AC (property: containment is real, not string matching):* a truth table of ≥40 cases in CI, including — a `training` grant answers "may I fine-tune" **yes**; a `training` grant answers "may I use as human reference" **yes**; a `human_reference` grant answers "may I train" **no**; a commercial-permitted grant answers a non-commercial request **yes** (containment runs one way only); a territory-limited grant answers an out-of-territory request **no**; an expired grant answers everything **no**; two overlapping grants from the same counterparty resolve to the union of permitted requests (must be fully contained by at least one single grant, never merged per-dimension).
- **HOD-107** **Scope lattice — revocation interaction.** Revoke-then-regrant-narrower must resolve to the narrower scope, and a mid-term revocation must leave `resolve(grant_id, at=t_before)` unchanged. *AC (property: revocation narrows the present without rewriting the past):* the same query at two timestamps returns different, individually correct answers, with both events visible in the log.

### Phase 2 — The four agents and the gateway (Aug 10–17) — plan first
- **HOD-301** Vertex access, pinned model IDs, temperature 0, durable shared response cache.
- **HOD-302** Antigravity agent definitions per §3.2, each with a distinct SA and a registry entry.
- **HOD-303** **Gemma triage on crawler logs** — classify access records as bot/human/unknown before Gemini sees anything, with measured volume reduction. Runs serverless on Vertex AI (`gemma-4-26b-a4b-it-maas`, pinned, per-token) with Ollama and a heuristic as ordered fallbacks. **Not load-bearing.** *AC:* triage rate in `metrics.json`. *Corrected 2026-08-07: the original local-Ollama/one-hour-Vertex-proof plan is superseded by serverless Gemma, which was probed reachable and now classifies live records in the scheduled accrual audit.*
- **HOD-310** **Rights custodian**: registration, terms authoring, control-tier management. *AC:* holds identity; has no read path to buyer terms.
- **HOD-311** **Licensing negotiator**: resolves a buyer scope request against the lattice, returns a licensable set with exclusions explained and a signed receipt. **Scoped to one `counterparty_id` per session by IAM.** *AC (property: confidentiality is enforced, not promised):* the negotiator's SA receives `PERMISSION_DENIED` reading any other counterparty's grants — a deployed test, not a doc diff.
- **HOD-312** **Agent Gateway**: every inter-agent call routed and policy-checked; denials logged as events, never silent. *AC:* a call violating a scope boundary appears in the log as a denial with the policy that rejected it.
- **HOD-313** **Prompt Inspector (local regex) on post-extraction bytes** of every inbound buyer document. Detection emits `InjectionDetected` + an anomaly item; **the request proceeds under its original scope**. *AC:* the poisoned scope-request fixture is caught every run and does not alter the returned set.
- **HOD-317** **Wall-clock measurement.** *AC:* the two live video beats — buyer scope request with the Prompt Inspector catch, and the revocation cascade — are each timed **three times on the deployed path, with variance recorded** to `metrics.json`. You get one take; you need the worst case, and §6's ladder is denominated in seconds that must be real.
- **HOD-320** **Evidence agent**: crawler-log analysis, canary checks, verbatim matching against a queryable model, redistribution checks. **`verbatim_match` is the only class requiring an external model surface** — if unavailable or unreliable, it is cut third on the §7 ladder and the class is stated in the README as designed-but-not-demonstrated, which is a limit, not a failure. Emits typed `EvidenceRecord`s with `claim_limit` on every one. *AC (property: it cannot overclaim):* a render-time lint rejects "trained on" / "was in the training set" / "proves training" in any generated text; no code path produces a cross-class total.
- **HOD-330** **Agent Registry**: agents published with version, scope, owning function; discoverable and invocable by role. *AC:* a role query returns only agents that role may invoke.
- **HOD-331** **Memory Bank**: long-lived grant/scope/revocation state surviving instance death and cold start. *AC:* a resolve after a cold start returns identical state to a warm one.
- **HOD-340** **OTel traces** end-to-end; every agent decision carries a span with the agent identity, the policy consulted, and the outcome. *AC:* a single trace shows a scope request traversing gateway → negotiator → registry → log, with the denial spans visible.
- **HOD-341** **Supervisor — detection and bounding.** Per-agent wall-clock deadline; a per-agent circuit breaker tripping after N consecutive failures; `TaskAbandoned{agent, reason: deadline | breaker | scope_violation}` written **by the supervisor**, never by the failing agent (the process that would report the failure is the process that failed). *AC (property: a stalled agent is detected without its cooperation):* an agent hard-killed mid-call is marked abandoned within its deadline, with no event written by the killed process.
- **HOD-342** **Supervisor — quarantine and reroute.** A quarantined agent is deregistered from the Registry for the remainder of the run; its task is rerouted to a healthy instance or degraded to a stated partial result; the request still completes. *AC (property: a bad worker cannot stall the fleet):* a worker forced into a loop is quarantined, its task rerouted, the request completes, and the quarantine and reroute both appear as spans in a single OTel trace.

### Phase 3 — Revocation, buyer API, UI (Aug 18–22)
- **HOD-350** **Revocation propagator** — the hero. Computes affected grants, resolves downstream derivative scopes by containment, emits signed notices with receipts. Original grants remain visible, struck through, never deleted. *AC (property: revocation is a legal instrument, not a technical erasure):* the notice text states the grant is terminated and makes **no** claim about model removal; a lint asserts this on every generated notice.
- **HOD-360** **Buyer API**: signed scope requests, `/.well-known/hodi.json`, machine-readable license documents and receipts. **API only — no second UI.** *AC:* an unsigned request is rejected; a signed one returns a verifiable receipt.
- **HOD-370** Artist console: register, author scopes, see grants and evidence grouped **by class with no total**, revoke. Control tiers rendered distinctly. *AC:* all three tiers visible from the real corpus.
- **HOD-410** Deploy: services, Jobs, Scheduler (already running against a stub since Aug 8), per-agent SAs, `min-instances=0`, max capped.
- **HOD-411** Public surfaces read-only and rate-limited (Resources warns explicitly about public Cloud Run URLs draining credits). *AC:* an adversarial burst costs nothing.

**Aug 22 — recording-ready gate. Feature freeze at 23:59 regardless of outcome.** *(Amended 2026-08-14: freeze lifted for the Phase 5 scope by explicit owner decision — GATE.md §4. The recording-ready question moves with the work.)*

### Phase 5 — Judge-feedback hardening & the incident flagship (Aug 14–26) — v1.2

Every AC below names the property it proves. Before accepting any: *could this go green with the property false?*

- **HOD-701** **Work-scoped authorization.** The authorization tuple is `principal × work × requested scope × time → decision`. `ScopeRequest` carries a mandatory `work_id`; the gateway grant read is constrained by the **credentialed** `counterparty_id` AND the requested `work_id`; the evaluator receives only grants applicable to that work. A missing `work_id` is rejected, never inferred. *AC (property: a grant for one work can never authorize use of another):* adversarial suite — buyer holds a training grant for Work A → request for Work A permitted; the same buyer's identical request for Work B denied; a grant on Work B with insufficient scope denied; a `work_id` belonging to another artist's work denied; a request omitting `work_id` rejected at the schema. All asserted through the real request path, not a re-implementation.
- **HOD-702** **Temporal containment.** The requested license window must be contained by the grant window: `request.valid_from ≥ grant.valid_from`, and where the grant is bounded, `request.valid_until ≤ grant.valid_until`; an open-ended request is contained only by an unbounded grant. Malformed intervals (`valid_until < valid_from`) are rejected at the schema. *AC (property: a grant can never authorize a window it does not cover):* a grant valid through September, asked in August for rights through December, is **denied** even though the evaluation instant is inside the grant; truth-table cases cover both bounds, open-ended requests, and malformed intervals.
- **HOD-703** **Assertion authority.** What an agent may *claim* is policy, declared as data beside the collection policy and enforced at the gateway. Assertion classes are a closed vocabulary; **no training-membership class exists**, so the claim is structurally inexpressible as an assertion, exactly as it is in the evidence schema. *AC (property: an agent structurally cannot claim beyond its epistemic authority):* the evidence agent submitting a causal-training assertion is refused with a structured denial naming the policy; the authority matrix rendered in docs is generated from the same data the gateway consults.
- **HOD-704** **Consent Arbiter.** A fifth agent holding **none** of the four conflict domains. It receives only typed assertions plus a policy version — no raw evidence, no identity, no commercial terms — and evaluates deterministically. *AC (property: the adjudicator can conclude only what typed assertions support):* given a crawler-access assertion and a no-applicable-grant assertion, the arbiter establishes `ACCESS_OUTSIDE_DECLARED_POLICY` and returns `MODEL_TRAINING_OCCURRED: NOT_ESTABLISHED`; the conclusion enum cannot express training membership; the arbiter has no write path to grant history.
- **HOD-705** **Incident state machine, containment, manifest.** Observation → investigation (each agent answering only within its wall) → adjudication → containment → signed manifest. Containment acts **only on what Hodi administers**: pending negotiations for the principal are frozen (a frozen principal's license request is refused with a structured event) and affected grants are revoked through the existing cascade; notices go through the outbox. The manifest carries observations, evidence hashes, policy version, grant-state hash, decision basis, stated limitations, agents involved, trace id, and the previous event hash. *AC (property: an incident's record can be independently reconstructed):* `hodi verify` rebuilds and confirms the decision from the manifest alone; the demo beat runs offline from fixtures.
- **HOD-706** **Cryptographic provenance.** Asymmetric signing of manifests, notices and receipts: Cloud KMS on the live path; an in-process, explicitly-labelled **ephemeral** Ed25519 key for the credential-free demo; the historical `UNSIGNED_PLACEHOLDER`/`SIG_REVOKED` documents remain untouched in the append-only log. *AC (property: a receipt can be verified by a party that could not have forged it):* verification uses only the public key; a single tampered byte fails; no new code path emits a signature-looking string that nothing can verify.
- **HOD-707** **Execution leases.** The supervisor issues a lease at dispatch and revokes it at quarantine/deadline; every supervised side-effecting write checks lease validity immediately before committing. Lease state is itself a fold over appended lease events. *AC (property: an abandoned worker cannot commit after quarantine):* a worker hard-hung past its deadline, then woken, attempts its write and receives a structured stale-lease denial; the standby's result stands; asserted with a real hung worker.
- **HOD-708** **Revocation idempotency.** Every revocation carries an `operation_id`; event and notice ids derive from it, so replays collide on `create()` instead of duplicating; the revocation event and the notice-pending outbox record are committed together; delivery is a separate, retryable step whose result is appended. *AC (property: retrying a failed revocation cannot double its effects):* a simulated crash after the first effect, followed by a full retry, yields exactly one notice and one revocation event.
- **HOD-709** **Durable Agent Registry.** Publications carry version, endpoint, service account, capabilities, status, `registered_at`, `last_heartbeat`; registrations, heartbeats and deregistrations are appended events over a pluggable store (Firestore live, in-memory offline); discovery folds them. Role-scoped non-disclosure is preserved. *AC (property: discovery reflects durable publications, not process memory):* a fresh process folds the same registry state a prior process published (live-Firestore E2E); quarantine deregistration is an appended event.
- **HOD-710** **Memory Bank persistence.** The class reads through the same pluggable event store; cold-start re-hydration is a property of the class under test, not of an unrelated code path. *AC (property: memory survives instance death through the class under test):* append via one instance, resolve via a fresh instance backed by the same store → identical state (live E2E); the offline suite proves the fold path credential-free.
- **HOD-711** **Real workload identity.** Conflict domains map to **named Firestore databases**; each agent SA holds roles only on its domain's databases (per-database IAM), so a foreign-domain read fails at Google IAM, not at the application layer. The revocation worker deploys as its own Cloud Run service under the propagator SA — also the killable isolation boundary. *AC (property: a workload literally lacks credentials for a foreign conflict domain):* the deployed licensing-path identity receives `PERMISSION_DENIED` **from IAM** reading identity-domain data, asserted E2E against the deployed infrastructure. Provisioning is one scripted command; row-level scoping (`counterparty_id`) remains gateway-enforced and is stated as such.
- **HOD-712** **Red-team drill.** One command runs five attacks: an injected buyer instruction; a compromised negotiator reading artist identity; the evidence agent asserting training membership; a rogue worker committing after lease revocation; a tampered incident package failing verification and verifying again after restore. *AC (property: the boundaries hold under deliberate attack):* every attack ends in the correct structured refusal, the legitimate transaction still completes, and the drill runs offline in CI.
- **HOD-713** **Constrained negotiation.** A buyer agent proposes; Hodi counteroffers deterministically by clamping the request to the per-work artist policy (territory intersection, duration cap, forced attribution, prohibited uses); insistence beyond policy yields `COUNTEROFFER_REJECTED_BY_POLICY`; agreement issues a grant through the normal event path. Scope terms only — no payments, no escrow. *AC (property: negotiation can never exceed the policy lattice):* model output can alter prose but no test input, adversarial or cooperative, produces an agreed scope outside the policy clamp.
- **HOD-715** **Deployment claims are derived, not remembered.** `docs/deployment_status.json` is the machine-readable state of every deployed capability; `scripts/deployment_status.py` renders and validates it, and `make check-docs` fails when the documents disagree with it. *AC (property: a deployment claim cannot outlive its evidence):* a capability marked `verified` without both an evidence source and a verification date is rejected by the validator; a capability marked never-run that carries a verification date is rejected; and the README's KMS disclaimer is required while unverified and **forbidden** once verified — bidirectional, so the prose cannot rot in either direction. All three rules mutation-tested.
- **HOD-716** **Storage fails closed.** Unreachable durable storage is an outage, not an empty log. *AC (property: process-local data is never served as the append-only log):* with credentials unavailable and no declared offline run, gateway construction and `default_event_store()` both raise; under `HODI_OFFLINE=1` the in-memory path still works, and the dev-shell gcloud-token fallback is preserved. A suite-hygiene guard forbids a test from popping `HODI_OFFLINE` in cleanup, since that pollution is what the previous fail-open behaviour was hiding.
- **HOD-717** **Caller identity is bound, verifiable, and honestly labelled.** The gateway establishes who is calling before deciding what they may do: the service account must be the one `iam_policy.py` declares for the role, an OIDC path derives the role from a Google-signed token's verified email, and every identity is labelled `oidc_verified` or `in_process_trusted`. *AC (property: a role cannot be asserted by a caller that does not hold it):* presenting one agent's SA while claiming another's role is a structured denial; on the verified path the role is derived, not chosen; `HODI_REQUIRE_VERIFIED_IDENTITY=1` refuses the unverified category outright; and no source file outside the policy module may contain a hand-typed agent service account.
- **HOD-718** **Registration is a running operation, not a redeploy.** `POST /api/v1/works` is artist-credentialed and persists through the rights custodian; `/works` is a fold over registrations unioned with the committed corpus as a labelled seed. *AC (property: control tier cannot be talked into existence):* `control_tier` is derived from whether a proof was supplied and is not a request field, so no body reaches `verified_control` without a stored proof (HOD-105); `artist_id` comes from the credential; a taken `work_id` is a uniform 403; an unreachable registry serves the seed marked `registry_unavailable`, never as live state.
- **HOD-719** **A counterparty system honours the rail.** `scripts/buyer_client.py` consumes the published terms and verification key, verifies a receipt with the public key alone, gates its own use on that verification, and stops after revocation. *AC (property: another system actually stops):* after the artist revokes, both Hodi's answer and the buyer's own gate refuse, and the buyer's audit records why — run offline and guarded in CI.
- **HOD-720** **Live release verification writes the claim.** `.github/workflows/verify-live.yml` runs the deployed boundary proof, the live manifest check, the `HODI_E2E` suite and a real KMS sign/verify/tamper under Workload Identity Federation, then records the result into `deployment_status.json`. *AC (property: only a verification run may promote a capability):* `scripts/record_live_verification.py` is the sole promoter and refuses to leave the file in a state its own validator rejects; no long-lived service-account key exists in the repository or its secrets.
- **HOD-714** **Durable trace export.** Cloud Trace export gated on deployment env; console exporter remains the offline default; span attributes identical either way. *AC (property: a delegation is reconstructable from the backend):* one trace shows gateway → discovery → agents → effect, and the quarantine variant shows deadline → abandonment → lease revocation → reroute.
- **HOD-501** `make demo` — committed cache + emulator, **zero credentials**, deterministic; `make demo-live`; `make verify-scopes` (lattice truth table). *AC:* clean clone **on a different machine**, Aug 26.
- **HOD-505** **Two diagrams.** A "The Fleet": four agents, gateway, registry, with the four conflict boundaries drawn as walls, **and a labelled Antigravity (or ADK) box on the orchestration layer with the OTel exporter drawn off it** — the framework and the observability path are both mandatory-checklist items and both should be legible from the diagram alone. B "What Hodi will not say": the evidence classes as separate columns with a struck-through fifth column labelled *training-set membership — not determinable*. *AC:* every number traces to `metrics.json`.
- **HOD-506** Repo spin-up scripts and verification workflows for credential-free demonstration.
- **HOD-509** `## Findings and learnings` opened Aug 11, appended daily: crawler-log volume and Gemma triage rate, canary results, verbatim-match hit rate, scope-lattice edge cases found, **and the Antigravity headless/OTel findings**. *AC:* ≥12 dated entries; ≥4 Google-toolchain findings actionable by the team that owns the tool.
- **HOD-510** **Make the toolchain evidence reachable.** `## Technologies used` names Antigravity, ADK (fallback and the Aug 8 outcome), Gemini 3.5 Pro/Flash with pinned IDs, and Gemma, each with one line — and **links `docs/BUILD-LOG.md` and `docs/antigravity/decision.md`, the latter with the boolean assertion quoted inline.** This is the most externally valuable artifact this project produces for a Fleet judge and it must not sit in a folder someone has to find. *AC (property: the build evidence is reached, not merely stored):* both links above the fold of `## Technologies used`; the assertion and its observed result quoted in the README itself; the Devpost technologies field mirrors it.
- **HOD-601** Video beat 1: Cold open on author's registered work.
- **HOD-602** Video beat 2: Agent Registry and conflict boundaries.
- **HOD-603** Video beat 3: Live buyer scope request with Prompt Inspector catch.
- **HOD-604** Video beat 4: Revocation cascade hero demonstration.
- **HOD-605** Video beat 5: OTel trace waterfall view.
- **HOD-606** Video beat 6: Supervisor quarantine and reroute.
- **HOD-607** Video beat 7: Diagram B honesty statement.
- **HOD-608** Video beat 8: GCP Cloud Run console and Vertex log proof.
- **HOD-620** Teaser social post on Aug 20.
- **HOD-621** Technical blog post drafted Aug 12–13, published Aug 28.
- **HOD-622** Devpost project description and form fields complete.
- **HOD-623** Gemma integration documentation and video proof.
- **HOD-624** Launch social post on Aug 30 naming Hodi.

---

## 5. Hard rules

| Rule | Why |
|---|---|
| **Every adversary in every fixture is a fictional, unnamed scraper.** No real company appears as a violator in the repo, video, blog, or social post — and never Google. | The framing decides whether this is a sponsor story or a sponsor liability. One frame showing a real crawler being caught undoes the entire positioning. |
| Never claim training-set membership. | Unsolved problem; a technical judge knows within thirty seconds. |
| Never imply revocation removes work from a model. | It terminates a grant. Anything more is false. |
| Never render an aggregate across evidence classes. | Honest tiers collapse into a dishonest number the moment they're summed. |
| Lead artist-side; architect two-sided. | The story and the Unlikely Hero are artist-side; the API surface is buyer-side. |

## 6. Video — target **3:30**, hard cap 4:00, **30 seconds of insurance**

Eight proofs is too many for 3:40 with an uncompressible 45-second hero. Budget them, then pre-commit the ladder.

| Beat | Seconds |
|---|---|
| Cold open on the author's own registered work — real essays, real recordings, terms attached. Thesis as a burned-in lower third at **0:08** (zero narration cost). | 15 |
| Registry + gateway + the four conflict walls | 20 |
| **Live buyer scope request**, with Prompt Inspector catching the poisoned document **inside the same window** and the request completing under its original scope. Burned-in wall clock. | 35 |
| **HERO — revocation cascade.** One click; affected grants light up; containment resolves downstream scopes; signed notices and receipts generate; the original grant remains struck through, never deleted. | 45 |
| OTel trace of that cascade, agent identities visible | 20 |
| Supervisor quarantines a looped worker; the request still completes | 20 |
| **Diagram B — the honesty beat.** *"Here is what Hodi will not tell you."* | 15 |
| GCP proof: Cloud Run console, Scheduler history, Vertex log with the pinned model ID in a callout box | 15 |
| Close on the thesis | 10 |
| Transitions | 15 |
| **Total** | **210 (3:30)** |

**Seconds-denominated cut order, deepest reserve first — a build cut on Aug 22 cannot recover runtime on Aug 27:**
1. GCP proof → fold the Vertex callout into the live-request window; console as a 5s frame (**−10s**)
2. Supervisor beat → 10s, quarantine and reroute only, no setup (**−10s**)
3. OTel trace → 10s, one span expanded rather than the full waterfall (**−10s**)
4. Registry + walls → 12s, Diagram A held with narration over it (**−8s**)
5. Cold open → 10s, one burned-in stat card (**−5s**)

**Never cut:** the revocation cascade at 45 seconds; the Prompt Inspector catch landing live inside the request window; Diagram B; the thesis at 0:08 and at close; the wall clock's continuity.

## 9. Prize notes

**Fleet is the category and the floor.** It has the most explicit mandatory checklist in the contest, and §2 answers all seven items with mechanisms. Do not reposition to Taskmaster or Collaborative Partner; the fit exists but is weaker, and repositioning forfeits the checklist advantage.

**Portfolio positioning.** Recorded outside this repository. Neither entry should be built or framed toward it.

**Not targets:** Startup Excellence (individual entry; and §1.4's no-PMF rule stands — do not relitigate it), Best Multimodal UX. Best Architectural Design is a consolation at a quarter the value of the category prize — maximize the architecture score because it is 30% of every path that matters, not because of the $5k.

## 7. Cut list
**Cut now:** payments, escrow, marketplace UI, takedown automation, any second front-end, Veo/Lyria.
**Aug 14 / Aug 22 abort order:** Gemma Vertex proof (keep Ollama + diagram + README) → redistribution evidence class → canary class (keep the mechanism documented) → artist console polish → verbatim-match class.
**Never on the abort list:** the four conflict boundaries and their negative tests, the revocation cascade, the honesty invariants and their lints, Diagram B, `make demo`, the README, the blog, the social posts, `## Findings and learnings`.

## 8. Build toolchain
Karani's §8 applies unchanged: **Gemini at runtime, exclusively**; Antigravity as the build and orchestration environment with ADK pre-committed as the fallback; every shipped prompt iterated in-family; long-context passes for whole-repo audits; `/docs/BUILD-LOG.md` with verbatim prompts, outcomes, and 2–3 key decisions per session. The highest-value findings here are **Antigravity's multi-agent scoping and OTel span emission**, which is the least externally documented surface in the SDK and the one a Fleet judge will most want to read about.
