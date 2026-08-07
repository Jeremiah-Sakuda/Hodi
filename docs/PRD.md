# Hodi — Product Requirements Document

**Version:** 1.1 · **Date:** Aug 5, 2026 · **Owner:** Jeremiah Sakuda
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
| Gemini 3.5+ via Vertex AI | Gemini 3.5 Pro (scope reasoning, term interpretation, evidence classification) + Flash (high-volume log triage); pinned model ID literals | HOD-301 |
| ≥1 Google Agent Framework | **Antigravity SDK** (four agents + supervisor); **ADK dual-listed as the fallback**, decided Aug 8 | HOD-020, HOD-302 |
| ≥1 Google Cloud infra service | Cloud Run services + Jobs, Firestore, Cloud Scheduler, Cloud Logging/Trace | HOD-005, HOD-410 |
| New project in Submission Period | Public remote from first commit, unsquashed; pre-Aug-3 audit; **`## Relationship to my other submissions`** disclosing the shared claim-record lineage by path and date | HOD-001, HOD-002, HOD-004, HOD-006 |
| Category | The Fortified Enterprise Fleet | — |
| **Fleet: cataloged for cross-department use** | **Agent Registry** — agents published with versions, scopes, and owning function; discoverable and invocable by role | HOD-310, HOD-330 |
| **Fleet: context across weeks of async operation** | **Memory Bank** — grants, scopes, and revocations are long-lived state with temporal validity; the registry survives instance death; crawler logs accumulate for weeks | HOD-101, HOD-102, HOD-103, HOD-320, HOD-331 |
| **Fleet: production data without violating policy** | **Agent Identity** (per-agent scoped SAs), **Agent Gateway** (routing + policy enforcement at the boundary), **Prompt Inspector** (local regex on untrusted buyer documents) | HOD-102, HOD-311, HOD-312, HOD-313, HOD-340 |
| **Fleet: audit reasoning** | **Agent Observability** — OpenTelemetry traces end-to-end; every agent decision carries a span; the trace is a demo artifact, not a log file | HOD-340 |
| **Nexus: failure tolerance** | Supervisor quarantine + reroute on loop, timeout, or scope violation; per-agent circuit breaker; `TaskAbandoned` on deadline; revocation propagation | HOD-341, HOD-342, HOD-350 |
| Devpost — features/functionality | `docs/devpost-description.md` §1 | HOD-622 |
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
- **HOD-005** Budget alerts at **$25/$50/$100/$140**; Gemma endpoint fenced in a **separate project with a $20 hard cap** and an unconditional 23:00 nightly teardown job; `trap`-based teardown. *AC:* teardown on a nonexistent endpoint is a verified no-op.
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
- **HOD-303** **Gemma triage on crawler logs** — classify access records as bot/human/unknown before Gemini sees anything, with measured volume reduction. Dev via local Ollama; Vertex proof once in Phase 5, torn down the same hour. **Not load-bearing.** *AC:* triage rate in `metrics.json`.
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

**Aug 22 — recording-ready gate. Feature freeze at 23:59 regardless of outcome.**

### Phase 4 — Docs, video, bonus (Aug 23–30)
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
