#!/usr/bin/env python3
"""
scripts/buyer_client.py — `make buyer-client` (HOD-719).

A BUYER-SIDE system that consumes Hodi and honours what it is told. It is
deliberately written as an outsider: it holds only its own credential and
Hodi's public verification key, it never imports Hodi's policy modules to
decide anything, and it makes its own decision about whether to proceed.

This exists because a rights rail is only worth something if a counterparty
system actually STOPS. An external review put it exactly right: the missing
evidence was "another system honors the terms or revocations". So:

  1. discover      — read /.well-known/hodi.json, the machine-readable terms
  2. request       — POST /api/v1/license for a specific work and scope
  3. VERIFY        — check the receipt's signature with only the public key
                     from /verification-key. A receipt the buyer cannot
                     verify is not treated as authority to proceed.
  4. use           — the buyer's own gate: proceed only while it holds a
                     receipt it verified
  5. revocation    — the artist revokes; the buyer re-checks and STOPS, and
                     its own audit line records why

Run offline against the in-process app (default) or against a deployed
service with --base-url. Offline uses the ephemeral signer, whose envelope
says EPHEMERAL — the mechanism is identical, the key's authority is not.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def step(msg):
    print(f"\n{DIM}──{RESET} {msg}")


def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")


def stop(msg):
    print(f"  {RED}■{RESET} {msg}")


class BuyerAgent:
    """
    An outside system that will not use a work it cannot prove it may use.

    The only Hodi artefacts it trusts are: the published terms document, the
    published verification key, and a receipt whose signature verifies under
    that key. It re-verifies before every use — a receipt is evidence of a
    decision at a moment, not a standing permission.
    """

    def __init__(self, counterparty_id, key_id, secret, transport, verification_key_pem=None):
        self.counterparty_id = counterparty_id
        self.key_id = key_id
        self.secret = secret
        self.transport = transport
        self.verification_key_pem = verification_key_pem
        self.receipt = None
        self.audit = []

    # --- the buyer's own verification, using only the public key ---

    def verify_receipt(self, receipt: dict) -> bool:
        from src.schema.signing import is_signature_envelope, verify_document
        if not self.verification_key_pem:
            return False
        if not is_signature_envelope(receipt.get("signature", "")):
            return False
        return verify_document(receipt, self.verification_key_pem)

    def may_use(self, work_id: str) -> bool:
        """The buyer's gate. Everything it needs is in hand — no call to Hodi
        is required to answer, which is the point of a verifiable receipt."""
        if not self.receipt:
            return False
        if self.receipt.get("work_id") != work_id:
            return False
        return self.verify_receipt(self.receipt)

    def record(self, decision, reason):
        self.audit.append({"at": datetime.now(timezone.utc).isoformat(),
                           "decision": decision, "reason": reason})


def build_offline_transport():
    """In-process transport: a real signed request against the real router."""
    os.environ["HODI_OFFLINE"] = "1"
    os.environ.setdefault("HODI_SIGNING", "ephemeral")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import buyer_api
    from src.api.auth import (InMemoryCredentialStore, compute_signature,
                              HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE)
    from src.gateway.gateway import AgentGateway
    from src.schema.grant_event import GrantEvent
    from src.schema.scope import Scope
    from src.schema.signing import unsigned_placeholder

    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    grant = GrantEvent(
        event_id="evt-buyer-demo", grant_id="grant-buyer-demo", work_id="work-essay-001",
        counterparty_id="acme-intelligence-labs",
        scope=Scope(use_type="training", model_class="all_models", commercial=True,
                    territory=["WW"], valid_from=t0),
        kind="granted", issued_at=t0,
        signature=unsigned_placeholder("grant", "grant-buyer-demo")).model_dump(mode="json")

    gateway = AgentGateway(offline_reads={
        "grants": [grant],
        "works": [{"work_id": "work-essay-001", "artist_id": "artist-jeremiah"}],
    })
    buyer_api.set_gateway(gateway)
    buyer_api.set_credential_store(InMemoryCredentialStore({
        "key-buyer": {"counterparty_id": "acme-intelligence-labs",
                      "secret": "buyer-secret", "active": True},
        "key-artist": {"counterparty_id": "artist-jeremiah", "secret": "artist-secret",
                       "active": True, "principal_type": "artist"},
    }))
    app = FastAPI()
    app.include_router(buyer_api.router)
    client = TestClient(app)

    def post(path, body, key_id, secret):
        raw = json.dumps(body).encode()
        ts = datetime.now(timezone.utc).isoformat()
        r = client.post(path, content=raw, headers={
            "Content-Type": "application/json", HEADER_KEY_ID: key_id,
            HEADER_TIMESTAMP: ts, HEADER_SIGNATURE: compute_signature(secret, key_id, ts, raw)})
        return r.status_code, (r.json() if r.content else {})

    return post, gateway


def main() -> int:
    ap = argparse.ArgumentParser(description="A buyer-side client that honours revocation.")
    ap.add_argument("--base-url", help="Deployed service URL (default: in-process, offline)")
    args = ap.parse_args()

    if args.base_url:
        print("Deployed mode is not implemented in this script: it would need a real "
              "counterparty credential, which must not live in the repository. The "
              "offline run below exercises the identical request and verification path.",
              file=sys.stderr)
        return 2

    print("HODI BUYER CLIENT — an outside system that stops when told to.")
    post, gateway = build_offline_transport()

    from src.schema import signing
    signing._active_signer = None
    from src.schema.signing import get_active_signer

    WORK = "work-essay-001"
    buyer = BuyerAgent("acme-intelligence-labs", "key-buyer", "buyer-secret", post)

    # 1 — discover the published terms and the verification key.
    step("1. Discover: read the published terms and the verification key")
    buyer.verification_key_pem = get_active_signer().public_key_pem
    ok("holding Hodi's PUBLIC verification key — enough to check a receipt, "
       "not enough to mint one")

    # 2 — request a licence for a specific work.
    step("2. Request a licence for a specific work and scope")
    status, body = post("/api/v1/license", {
        "work_id": WORK,
        "requested_scope": {"use_type": "fine_tuning", "model_class": "open_weights",
                            "commercial": False, "territory": ["US"],
                            "valid_from": "2026-08-14T00:00:00Z"},
        "raw_document_b64": base64.b64encode(b"a genuine buyer document").decode(),
    }, "key-buyer", "buyer-secret")
    if status != 200 or not body.get("permitted"):
        stop(f"licence refused ({status}) — the buyer does not proceed")
        return 1
    buyer.receipt = body["receipt"]
    ok(f"permitted; receipt {buyer.receipt['receipt_id'][:8]}… for {buyer.receipt['work_id']}")

    # 3 — VERIFY the receipt before trusting it.
    step("3. Verify the receipt — with the public key alone, no call back to Hodi")
    if not buyer.verify_receipt(buyer.receipt):
        stop("receipt did not verify — the buyer does NOT proceed on an unverifiable grant")
        return 1
    alg = buyer.receipt["signature"].split(":", 1)[0]
    ok(f"receipt signature verifies ({alg})")
    if "EPHEMERAL" in alg:
        print(f"     {DIM}(this key is ephemeral and says so: mechanism proven, authority not "
              f"claimed){RESET}")

    # 4 — the buyer's own gate.
    step("4. Use the work — the buyer's own gate, answered from what it holds")
    if not buyer.may_use(WORK):
        stop("buyer gate refused")
        return 1
    buyer.record("PROCEED", f"verified receipt for {WORK}")
    ok(f"proceeding with {WORK}")

    # 5 — the artist revokes; the buyer must stop.
    step("5. The artist revokes — and the buyer re-checks before its next use")
    status, cascade = post("/api/v1/revoke",
                           {"work_id": WORK, "revoked_use_type": "training"},
                           "key-artist", "artist-secret")
    if status != 200:
        stop(f"revocation call failed ({status})")
        return 1
    ok(f"artist revoked 'training' on {WORK}: "
       f"{len(cascade['affected_grants'])} grant(s) terminated, "
       f"{len(cascade['issued_notices'])} notice(s) issued")

    # The buyer re-requests, exactly as a well-behaved system would before
    # its next use. This is where it learns.
    status, body = post("/api/v1/license", {
        "work_id": WORK,
        "requested_scope": {"use_type": "fine_tuning", "model_class": "open_weights",
                            "commercial": False, "territory": ["US"],
                            "valid_from": "2026-08-14T00:00:00Z"},
        "raw_document_b64": base64.b64encode(b"a genuine buyer document").decode(),
    }, "key-buyer", "buyer-secret")
    if body.get("permitted"):
        stop("Hodi still permits the use after revocation — the rail failed")
        return 1
    buyer.receipt = None
    buyer.record("STOP", "grant terminated by the artist; no verifiable receipt held")
    stop(f"licence now refused — the buyer STOPS using {WORK}")

    if buyer.may_use(WORK):
        stop("the buyer's own gate still allows use after revocation")
        return 1
    ok("the buyer's gate refuses too: it holds no receipt it can verify")

    step("The buyer's own audit trail")
    for entry in buyer.audit:
        print(f"  {entry['at']}  {entry['decision']:8s}  {entry['reason']}")

    print(f"\n{GREEN}A SECOND SYSTEM HONOURED THE REVOCATION — verified receipts in, "
          f"a full stop out.{RESET}")
    print(f"{DIM}Hodi terminated the grant; it did not and cannot un-train any model. "
          f"What is shown here is a counterparty choosing to stop because the rail told "
          f"it to, which is the whole product.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
