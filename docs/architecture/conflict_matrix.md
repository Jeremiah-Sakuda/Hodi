# Conflict-of-Interest IAM Permissions Matrix

This document is **GENERATED** directly from `src/schema/iam_policy.py`. Do not edit manually.

## Structural Invariant: Four Service Accounts & Four Conflict Boundaries

> **Rule:** No Service Account may hold two permissions from `{artist identity, buyer terms, evidence, revocation}`.

> **Paired Positive Enforcement:** Every cell asserting `DENIED` is tested alongside its corresponding `PERMITTED` operation in CI.


| Agent Role | Service Account Email | Conflict Domain | Permitted Collections (Positive) | Denied Collections (Negative) |
|---|---|---|---|---|
| **Rights Custodian** | `rights-custodian-sa@hodi-2026.iam.gserviceaccount.com` | `identity` | `works`<br>`artists`<br>`control_proofs` | `buyer_terms`<br>`crawler_access`<br>`canaries`<br>`revocation_notices` |
| **Licensing Negotiator** | `licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com` | `buyer_terms` | `buyer_terms/{counterparty_id}`<br>`receipts`<br>`grants` (Requires filter: `counterparty_id`)  | `artists`<br>`works`<br>`crawler_access`<br>`canaries`<br>`revocation_notices` |
| **Evidence Agent** | `evidence-agent-sa@hodi-2026.iam.gserviceaccount.com` | `evidence` | `crawler_access`<br>`canaries`<br>`evidence_records` | `artists`<br>`buyer_terms`<br>`grants`<br>`revocation_notices` |
| **Revocation Propagator** | `revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com` | `revocation` | `grants`<br>`revocation_notices` | `artists`<br>`buyer_terms`<br>`crawler_access`<br>`canaries` |

---

## Judge Verification (Under 30 Seconds)

Inspect `src/schema/iam_policy.py` and `tests/test_*_iam.py` to verify that each SA receives `PERMISSION_DENIED` on forbidden collections while successfully performing permitted operations.
