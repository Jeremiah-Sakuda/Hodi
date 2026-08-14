#!/usr/bin/env python3
"""
scripts/hodi_verify.py — independent verification of Hodi's signed documents
(HOD-706), and of full consent-incident packages (HOD-705).

    python3 scripts/hodi_verify.py <document.json> --key <public_key.pem>
    python3 scripts/hodi_verify.py <incident_package.json>   # key embedded

The point of this script is WHO DOES NOT RUN IT: Hodi. Verification uses
only the document bytes and a public key — no Hodi service, no Firestore,
no credentials — so a counterparty, a court, or a judge can check a receipt
Hodi could not repudiate and they could not forge.

Checks, per document kind:
  * any signed document — canonical bytes (without `signature`) verify
    against the envelope under the given key; placeholders and tampered
    bytes FAIL loudly and say why.
  * incident package    — additionally: every referenced observation's hash
    matches its evidence_hashes entry; the event-chain hash links; the
    decision is REPRODUCED from the package's typed assertions through the
    same deterministic arbiter policy, and must equal the recorded decision.

Exit code 0 = everything verified; 1 = any check failed; 2 = usage error.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema.signing import (  # noqa: E402
    is_signature_envelope, is_unsigned_placeholder,
    signable_bytes, verify_envelope, canonical_json_bytes,
)

GREEN_CHECK = "✓"
RED_CROSS = "✗"


def _p(ok: bool, label: str) -> bool:
    print(f"  {GREEN_CHECK if ok else RED_CROSS} {label}")
    return ok


def verify_signature_block(doc: dict, public_key_pem: str) -> bool:
    envelope = doc.get("signature", "")
    if is_unsigned_placeholder(envelope):
        print(f"  {RED_CROSS} signature is a labelled placeholder ({envelope.split(':', 1)[0]}) — "
              "nothing to verify, by design; this document predates signing or "
              "was issued without a configured signer")
        return False
    if not is_signature_envelope(envelope):
        print(f"  {RED_CROSS} signature field is neither an envelope nor a labelled "
              f"placeholder: {envelope[:40]!r}")
        return False
    ok = verify_envelope(envelope, signable_bytes(doc), public_key_pem)
    alg = envelope.split(":", 1)[0]
    return _p(ok, f"document signature valid ({alg})" if ok else f"document signature INVALID ({alg})")


def verify_incident_package(package: dict) -> bool:
    """Full incident-package verification — see src/incident/package.py for
    the exporter this mirrors. The public key ships INSIDE the package (with
    its authority class labelled); pass --key to override with one you trust
    out of band, which is the stronger posture."""
    from src.incident.package import verify_package  # local import: needs src/incident
    report = verify_package(package)
    for ok, label in report.checks:
        _p(ok, label)
    if report.conclusions:
        print("\n  Incident conclusions (reproduced and matching):")
        for claim, status in report.conclusions.items():
            print(f"    {claim}: {status}")
    return report.all_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a Hodi signed document or incident package.")
    ap.add_argument("document", help="Path to the JSON document")
    ap.add_argument("--key", help="Public key PEM path (required for bare documents; "
                                  "overrides the embedded key for incident packages)")
    args = ap.parse_args()

    path = Path(args.document)
    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text())

    print(f"hodi verify — {path.name}")
    if "incident_id" in doc and "manifest" in doc:
        if args.key:
            doc = dict(doc, verification_key_pem=Path(args.key).read_text())
            print("  (using operator-supplied key, overriding the embedded one)")
        ok = verify_incident_package(doc)
    else:
        if not args.key:
            print("A bare signed document needs --key <public_key.pem>", file=sys.stderr)
            return 2
        ok = verify_signature_block(doc, Path(args.key).read_text())

    print("\n" + ("VERIFIED" if ok else "VERIFICATION FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
