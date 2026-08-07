# AGENTS.md — Hodi

Context file for agentic coding sessions. Read this before touching any file. If an instruction here conflicts with a request in a session prompt, **stop and say so** rather than resolving it silently.

---

## What this is

Hodi is a governed fleet of agents that administers creative consent: registering works with proof of control, expressing scoped terms, negotiating with buyers under confidentiality, propagating revocations across affected grants, and keeping an audit record that never overclaims.

*Hodi* is what you call at someone's door before entering. **Hodi is the knock.**

**The problem, one sentence:** your voice is in a product you never agreed to, and there is no mechanism by which you could have agreed, refused, priced, or revoked.

`docs/PRD.md` is authoritative. Requirement IDs (`HOD-###`) and their acceptance criteria are the contract.

---

## The three honesty invariants — the product's spine

Everything else in this system is ordinary engineering. These three are why it is worth building, and each is enforced by structure, never by prose:

1. **Hodi never claims a work was in a training set.** Membership inference against frontier models is unsolved. The `EvidenceRecord.class` enum has **no such value**, so the schema cannot express the claim. Every record carries a literal `claim_limit` string. A render-time lint rejects "trained on", "was in the training set", and "proves training" in any generated text. If a task seems to require asserting training membership, the task is wrong.
2. **Revocation terminates a grant. It does not un-train a model.** Revocation is a legal instrument with technical enforcement of the *grant*, plus a dated signed notice and a receipt. Any copy implying removal from a model is struck, and a lint asserts this on every generated notice.
3. **Ownership is verified or explicitly not.** `control_tier` is mandatory: `verified_control` (with a stored `control_proof`), `asserted`, or `disputed`. The three render differently everywhere they appear, and `asserted` is never hidden. A system that confidently attributes rights to whoever typed first is worse than no system.

**And the fourth, which is a positioning rule with the force of an invariant: every adversary in every fixture is a fictional, unnamed scraper.** No real company appears as a violator in the repo, the video, the blog, or any social post — and never Google. This decides whether the project reads as infrastructure or as an accusation.

---

## Hard constraints

- **Runtime is Gemini, exclusively.** Gemini 3.5 Pro and Flash via Vertex AI, pinned model ID literals, temperature 0. No other model provider in any execution path.
- **The four agents are separated by conflict of interest, not by task.** The rights custodian holds artist identity. The licensing negotiator sees **one** counterparty per session and must be *incapable* of reading another's terms. The evidence agent must not see commercial terms, or its findings become interested. The revocation propagator must not hold identity. **No service account may hold two of {identity, buyer terms, evidence, revocation}.** A monolith here would itself be the violation — that sentence is the product's architectural thesis, so do not collapse agents "for simplicity."
- **The grant log is append-only, enforced by a custom IAM role** (`datastore.entities.create` + `get`; no `update`/`delete`) on every agent SA. Firestore security rules govern the artist's browser path only — they are never evaluated for server-SDK traffic and cannot be the pipeline's enforcement.
- **Revocation is a new event that supersedes.** The original grant is never deleted; it renders struck through. The audit trail's entire value is showing what *was* permitted at each moment.
- **`resolve(grant_id, at=t)` is the single read path** for grant state. Current state and historical state are the same fold with a different timestamp. Never add a second read path or a convenience cache the UI reads instead.
- **No aggregate across evidence classes.** No numeric field on `EvidenceRecord`, no scoring, no ordering, no total. Honest tiers collapse into a dishonest number the moment someone sums them.
- **Gateway denials are logged as events.** Never a silent refusal — a denial nobody can see is indistinguishable from a bug.
- **Truthful Build Log & Verification Rule.** An outcome in `docs/BUILD-LOG.md` may ONLY report what was empirically verified. Any infrastructure or command step whose success was not confirmed (or where errors were masked) MUST be logged strictly as `attempted-and-unverified`. Never use `|| true` on infrastructure commands whose failure changes application behavior.
- **Latency Measurement Surface Rule.** Any latency or timing figure recorded in `metrics.json` MUST explicitly state its measurement surface — `'deployed-over-network'` or `'in-process'`. A figure without that field is invalid. Measuring an in-process mock and reporting it as the deployed latency is a critical failure.
- **Literal Metric Rendering Rule.** No displayed metric (evidence counts, crawler figures, timing values, accrual numbers) may be a literal in the UI or docs. Every number shown to a user or written to a doc MUST be read from its source at render time. An unavailable source renders as "unavailable", never as a plausible stand-in or mock value.

---

## Acceptance-criterion discipline

> **An acceptance criterion that names the artifact it inspects, rather than the property it proves, will pass while the property fails.**

State the property first, then ask whether the test could go green with that property false.

Tests that must exist because the obvious version is insufficient:
- **Cross-buyer read:** the negotiator's deployed SA receives `PERMISSION_DENIED` reading any other counterparty's grants. A documentation diff is not a test.
- **Scope containment truth table**, ≥40 cases across all five dimensions simultaneously — not string matching, not one-dimension spot checks.
- **Temporal correctness:** the same query at two timestamps returns different, individually correct answers, with both events visible.
- **Supervisor detection without cooperation:** an agent hard-killed mid-call is marked abandoned *by the supervisor*, with no event written by the killed process.
- **The lints are adversarial:** seed the overclaim lint from paraphrases it was not written against ("this proves the model saw your work"), not from its own token list.

---

## Repo layout

```
docs/          PRD.md · GATE.md · BUILD-LOG.md · FINDINGS.md · compliance.md · metrics.json · antigravity/
src/schema/    work · scope · lattice.py (the partial order, declared as data) · grant_event · receipt · evidence
src/agents/    rights_custodian · licensing_negotiator · evidence_agent · revocation_propagator · supervisor
src/gateway/   routing, policy enforcement, denial events
src/registry/  agent publication, versioning, role-scoped discovery
src/resolve/   resolve(grant_id, at=t) — the single read path · permits(grant, request)
src/evidence/  crawler log ingest · gemma triage · canary · verbatim · redistribution
src/api/       signed buyer requests · /.well-known/hodi.json · receipts
src/console/   artist console (register, scope, grants, evidence by class, revoke)
fixtures/      buyer requests (incl. poisoned) · scope truth table · corpus manifest
scripts/       bootstrap_gcp.sh · teardown.sh · verify_scopes · prompt_bench.sh
```

## Commands

| Command | Contract |
|---|---|
| `make demo` | Clean clone, **zero credentials**, committed cache + emulator. README line 1. |
| `make demo-live` | Real Vertex path; documented cost and wall clock. |
| `make verify-scopes` | Prints the lattice table and runs the ≥40-case containment truth table. |
| `make metrics` | Regenerates `/docs/metrics.json`. Every number on either diagram traces here. |
| `make compliance` | Requirement IDs diffed against the matrix **and the prose**. |

---

## The two things that are real, and must stay real

**The corpus is the author's own published work** — essays, repos, bass recordings. Not synthetic. This is the only uncontrolled input in the author's entire portfolio and it is worth more than any feature. Never replace it with fixtures for convenience.

**The evidence endpoint has been logging real third-party access since Aug 6.** That accrual cannot be recovered later; if it goes down, it stops accruing and the loss is permanent. Treat uptime on that one service as a hard constraint, and never point it at fixture data.

---

## Non-goals — do not build these

No training-set membership detection (stated as a designed limit, with the reason). No adversarial perturbation. No takedown automation, litigation tooling, or enforcement actions — Hodi is a licensing rail, not a weapon. No payments, escrow, or marketplace UI. **No second front-end** — the buyer surface is a signed API with receipts; two UIs is how this becomes a 40-day build. No PMF or market-size argument anywhere.

## Session protocol

Every session ends with an entry appended to `docs/BUILD-LOG.md`:

```markdown
### YYYY-MM-DD — <session title>

**Prompt (verbatim):**
> <the prompt exactly as given, unedited>

**Outcome:** <what was built, what passed, what failed, what surprised>

**Key decisions:**
1. <decision> — <why, and what was rejected>
2. <decision> — <why, and what was rejected>

**Requirements touched:** HOD-###, HOD-###
```

Two or three decisions, each a fork where the alternative was live. If nothing forked, write "No forks this session" rather than manufacturing decisions.

Append to `docs/FINDINGS.md` daily: crawler-log volume and Gemma triage rate, canary results, scope-lattice edge cases discovered, verbatim-match hit rate, `spend_to_date` — and the **Google-toolchain findings**, above all **Antigravity's multi-agent scoping and OTel span emission**, which is the least externally documented surface in the SDK and the thing a Fleet judge will most want to read about.
