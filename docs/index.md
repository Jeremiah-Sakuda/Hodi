---
title: Hodi
---

# Hodi — Creative Consent Administration Fleet

*"Your voice is in a product you never agreed to."* **Hodi is the knock.**

Hodi is a governed fleet of institutional agents that administers creative consent: registering
works with proof of control, expressing scoped machine-readable terms, negotiating with buyers
under confidentiality, and propagating revocations across affected grants. Four agents separated by
conflict of interest, an append-only grant-event log, and honesty invariants enforced by schema
rather than by good intentions.

Created for the All Things Agentic Hackathon.

## Writing

- **[Seven ways to lie to yourself in code](blog/seven-ways-to-lie-to-yourself-in-code.html)** — the
  defect ledger: thirty-one defects, nine classes, the four that recurred, and the four structural
  guards that answer them.

## Project documents

- [Build log](BUILD-LOG.html) — every session's verbatim prompt, outcome, and forked decisions,
  including five dated correction notes.
- [Findings and learnings](FINDINGS.html) — daily observations plus two long-form named findings.
- [Antigravity SDK decision](antigravity/decision.html) — the boolean assertion, the observed
  result, and the branch taken.
- [Conflict-of-interest IAM matrix](architecture/conflict_matrix.html) — generated from the policy
  module the gateway reads.

## Source and live service

- Repository: [github.com/Jeremiah-Sakuda/Hodi](https://github.com/Jeremiah-Sakuda/Hodi)
- Evidence endpoint: [hodi-evidence-endpoint](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/)
- Machine-readable consent terms: [/.well-known/hodi.json](https://hodi-evidence-endpoint-406699565497.us-central1.run.app/.well-known/hodi.json)
