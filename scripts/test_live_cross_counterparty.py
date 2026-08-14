#!/usr/bin/env python3
"""
scripts/test_live_cross_counterparty.py — `make demo-live` (HOD-311, HOD-312, HOD-360).

Proves the cross-buyer confidentiality boundary over the public network, on the
DEPLOYED service, in two independent places:

  PART A — the gateway policy layer, via /api/v1/debug/compromised_agent_read:
    a properly scoped read succeeds with real documents; an unfiltered read and
    a cross-counterparty read are denied with structured PolicyDenialEvents.

  PART B — the PRODUCTION request path, via /api/v1/license:
    the unauthenticated cross-buyer attack that WORKED on 2026-08-07 is replayed
    verbatim and must now be refused.

  PART C — the MUTATING and INTERNAL routes:
    /api/v1/revoke shipped fully unauthenticated (anyone could terminate any
    published work_id, and append-only means it is not undoable), and
    /internal/accrual_audit shipped public and appended on every call. Both are
    replayed anonymously and must be refused.

Part B exists because Part A alone was misleading: the debug endpoint supplies
its own session context, so it could not have caught a production path that
took the caller's identity from the request body. A boundary test that cannot
fail the way production failed is not a boundary test.
"""

import sys
import json
import hmac
import hashlib
import requests
from datetime import datetime, timezone

BASE = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
DEBUG_URL = f"{BASE}/api/v1/debug/compromised_agent_read"
LICENSE_URL = f"{BASE}/api/v1/license"

# The counterparty whose data the attack tries to reach. It genuinely exists in
# the deployed grants collection, so a successful read would be a real leak.
VICTIM_COUNTERPARTY = "buyer-acme-2"

VICTIM_SCOPE = {
    "use_type": "training", "model_class": "all_models", "commercial": True,
    "attribution_required": False, "territory": ["WW"],
    "valid_from": "2026-08-07T00:00:00Z",
}


def part_a_gateway_policy():
    print("=" * 78)
    print("PART A — GATEWAY POLICY LAYER (/api/v1/debug/compromised_agent_read)")
    print("=" * 78)

    print("\n[A1] properly scoped read (must SUCCEED with real documents)...")
    r0 = requests.post(DEBUG_URL, json={"attack_type": "valid_read"}, timeout=60).json()
    print(json.dumps(r0)[:600])
    assert r0["status"] == "SUCCESS", "Gateway failed to allow properly scoped read!"
    assert r0["docs_returned"] >= 1, "Properly scoped read returned no documents!"

    print("\n[A2] unfiltered read (must be DENIED)...")
    r1 = requests.post(DEBUG_URL, json={"attack_type": "unfiltered"}, timeout=60).json()
    print(json.dumps(r1)[:400])
    assert r1["status"] == "DENIED", "Gateway failed to block unfiltered read!"

    print("\n[A3] cross-counterparty read (must be DENIED)...")
    r2 = requests.post(DEBUG_URL, json={"attack_type": "cross_counterparty"}, timeout=60).json()
    print(json.dumps(r2)[:400])
    assert r2["status"] == "DENIED", "Gateway failed to block cross-counterparty read!"


def signed_headers(key_id, secret, raw_body):
    ts = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(raw_body).hexdigest()
    sig = hmac.new(secret.encode(), f"{key_id}\n{ts}\n{digest}".encode(), hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Hodi-Key-Id": key_id,
            "X-Hodi-Timestamp": ts, "X-Hodi-Signature": sig}


def part_b_production_path():
    print("\n" + "=" * 78)
    print("PART B — PRODUCTION REQUEST PATH (/api/v1/license)")
    print("=" * 78)

    body = json.dumps({
        "counterparty_id": VICTIM_COUNTERPARTY,
        # work_id present so the replay still probes the AUTH layer after
        # HOD-701 made the field mandatory: without it the new schema refuses
        # the body as 422 before authentication ever runs, and the exploit
        # replay would be asserting the wrong boundary.
        "work_id": "work-essay-001",
        "requested_scope": VICTIM_SCOPE,
        "raw_document_b64": "aGVsbG8=",
    }).encode("utf-8")

    print(f"\n[B1] the 2026-08-07 exploit verbatim: no credential, bogus signature,")
    print(f"     claiming counterparty '{VICTIM_COUNTERPARTY}' (must be REFUSED)...")
    r = requests.post(LICENSE_URL, data=body, timeout=60, headers={
        "Content-Type": "application/json", "X-Hodi-Key-Id": "anything",
        "X-Hodi-Timestamp": datetime.now(timezone.utc).isoformat(),
        "X-Hodi-Signature": "NOT-A-REAL-SIGNATURE"})
    print(f"     HTTP {r.status_code}: {r.text[:220]}")
    assert r.status_code == 403, f"LEAK: unauthenticated cross-buyer request returned {r.status_code}!"
    assert "receipt_id" not in r.text, "LEAK: a receipt was issued to an unauthenticated caller!"

    print("\n[B2] no signature headers at all (must be REFUSED)...")
    r = requests.post(LICENSE_URL, data=body, timeout=60,
                      headers={"Content-Type": "application/json"})
    print(f"     HTTP {r.status_code}: {r.text[:160]}")
    assert r.status_code == 403, f"LEAK: unsigned request returned {r.status_code}!"

    print("\n[B3] well-formed signature under a key the attacker invented (must be REFUSED)...")
    headers = signed_headers("key-attacker-invented", "a-secret-nobody-registered", body)
    r = requests.post(LICENSE_URL, data=body, timeout=60, headers=headers)
    print(f"     HTTP {r.status_code}: {r.text[:160]}")
    assert r.status_code == 403, f"LEAK: forged credential returned {r.status_code}!"


def part_c_mutating_routes():
    print("\n" + "=" * 78)
    print("PART C — MUTATING AND INTERNAL ROUTES (/api/v1/revoke, /internal/accrual_audit)")
    print("=" * 78)

    # A work_id that matches nothing, so a regression here still writes no events.
    body = json.dumps({"work_id": "nonexistent-work-probe-only",
                       "revoked_use_type": "training"}).encode("utf-8")

    print("\n[C1] anonymous revocation (must be REFUSED)...")
    r = requests.post(f"{BASE}/api/v1/revoke", data=body, timeout=60,
                      headers={"Content-Type": "application/json"})
    print(f"     HTTP {r.status_code}: {r.text[:160]}")
    assert r.status_code == 403, f"LEAK: anonymous revocation returned {r.status_code}!"

    print("\n[C2] revocation signed by a forged credential (must be REFUSED)...")
    r = requests.post(f"{BASE}/api/v1/revoke", data=body, timeout=60,
                      headers=signed_headers("key-attacker-invented", "unregistered-secret", body))
    print(f"     HTTP {r.status_code}: {r.text[:160]}")
    assert r.status_code == 403, f"LEAK: forged revocation credential returned {r.status_code}!"

    print("\n[C3] internal accrual audit without the Scheduler's OIDC token (must be REFUSED)...")
    r = requests.get(f"{BASE}/internal/accrual_audit", timeout=60)
    print(f"     HTTP {r.status_code}: {r.text[:160]}")
    assert r.status_code == 403, f"LEAK: anonymous accrual audit returned {r.status_code}!"


if __name__ == "__main__":
    part_a_gateway_policy()
    part_b_production_path()
    part_c_mutating_routes()
    print("\n" + "=" * 78)
    print("ALL LIVE BOUNDARY TESTS PASSED — gateway policy AND production request path.")
    print("=" * 78)
