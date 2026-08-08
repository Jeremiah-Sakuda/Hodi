#!/usr/bin/env python3
"""
scripts/seed_counterparty_credential.py — register a signing credential for a
counterparty (HOD-360).

A counterparty's identity on the buyer API comes from a VERIFIED CREDENTIAL,
never from a field in the request body. This registers the shared secret that
binds a `key_id` to a `counterparty_id`.

The secret is generated here, printed ONCE, and stored in Firestore under
`counterparty_credentials/{key_id}`. It is never logged again and never
returned by any API surface.

Credentials carry a `principal_type`:
  counterparty — may negotiate licenses (/api/v1/license, /api/v1/license/natural)
  artist       — may revoke (/api/v1/revoke)
A buyer credential must not be able to terminate an artist's grants, so the
routes require the matching principal type and refuse the other.

Usage:
    python3 scripts/seed_counterparty_credential.py <counterparty_id> [key_id] [principal_type]
"""

import os
import sys
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore
from src.api.auth import CREDENTIAL_COLLECTION


def build_client(project_id: str) -> firestore.Client:
    try:
        return firestore.Client(project=project_id)
    except Exception:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        from google.oauth2 import credentials as oauth2_credentials
        return firestore.Client(project=project_id,
                                credentials=oauth2_credentials.Credentials(token))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    counterparty_id = sys.argv[1]
    key_id = sys.argv[2] if len(sys.argv) > 2 else f"key-{counterparty_id}"
    principal_type = sys.argv[3] if len(sys.argv) > 3 else "counterparty"
    if principal_type not in ("counterparty", "artist"):
        print(f"principal_type must be 'counterparty' or 'artist', got {principal_type!r}", file=sys.stderr)
        sys.exit(2)
    project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")

    db = build_client(project_id)
    secret = secrets.token_urlsafe(32)

    db.collection(CREDENTIAL_COLLECTION).document(key_id).set({
        "counterparty_id": counterparty_id,
        "secret": secret,
        "active": True,
        "principal_type": principal_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    snapshot = db.collection(CREDENTIAL_COLLECTION).document(key_id).get()
    if not snapshot.exists or snapshot.to_dict().get("counterparty_id") != counterparty_id:
        print("ERROR: read-back verification failed.", file=sys.stderr)
        sys.exit(1)

    print(f"Registered credential in project '{project_id}':")
    print(f"  key_id:          {key_id}")
    print(f"  counterparty_id: {counterparty_id}")
    print(f"  principal_type:  {principal_type}")
    print(f"  secret:          {secret}")
    print("\nThis secret is shown ONCE. Sign requests as:")
    print("  X-Hodi-Key-Id:     <key_id>")
    print("  X-Hodi-Timestamp:  <ISO-8601 UTC, within 300s>")
    print("  X-Hodi-Signature:  hex HMAC-SHA256(secret, f'{key_id}\\n{timestamp}\\n{sha256(raw_body)}')")


if __name__ == "__main__":
    main()
