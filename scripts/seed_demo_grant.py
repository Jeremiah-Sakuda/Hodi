#!/usr/bin/env python3
"""
scripts/seed_demo_grant.py — Seed the demo session grant (HOD-311 live proof).

Seeds one grant event for the demo session counterparty ('acme-intelligence-labs',
a fictional AI lab) over 'work-repo-001' — one of the five real registered corpus
works, and the one carrying a verified_control proof (signed commit).

This is the grant the properly scoped read in
/api/v1/debug/compromised_agent_read (attack_type=valid_read) returns, so the
SUCCESS case in scripts/test_live_cross_counterparty.py demonstrates a genuine
read of real data — not an empty set a stub could reproduce.

Idempotent: the document ID is the deterministic event_id, so re-running
overwrites the same document.
"""

import os
import sys
import subprocess
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore
from src.schema.grant_event import GrantEvent, generate_deterministic_event_id
from src.schema.scope import Scope

DEMO_COUNTERPARTY = "acme-intelligence-labs"
DEMO_WORK_ID = "work-repo-001"
DEMO_GRANT_ID = "grant-acme-il-001"


def build_client(project_id: str) -> firestore.Client:
    """ADC first; falls back to the gcloud CLI token for local dev shells without ADC."""
    try:
        return firestore.Client(project=project_id)
    except Exception:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        from google.oauth2 import credentials as oauth2_credentials
        return firestore.Client(project=project_id, credentials=oauth2_credentials.Credentials(token))


def seed_demo_grant():
    project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
    print(f"Connecting to Firestore project: {project_id}")
    db = build_client(project_id)

    issued_at = datetime.now(timezone.utc)
    event_id = generate_deterministic_event_id(DEMO_GRANT_ID, step=1, attempt=1)

    event = GrantEvent(
        event_id=event_id,
        grant_id=DEMO_GRANT_ID,
        work_id=DEMO_WORK_ID,
        counterparty_id=DEMO_COUNTERPARTY,
        scope=Scope(
            # `training`, the broadest use type, so the hero revocation of
            # `training` correctly terminates this grant AND the notice's
            # derived_scopes show all four uses it withdraws
            # (training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference).
            # A narrower grant (e.g. fine_tuning) must NOT be terminated by
            # revoking training — see the revocation-reach finding — so the demo
            # grant has to be held at the use being revoked for the beat to
            # demonstrate a correct, non-empty cascade.
            use_type="training",
            model_class="open_weights",
            commercial=False,
            attribution_required=True,
            territory=["US", "CA"],
            valid_from=issued_at,
            valid_until=None
        ),
        kind="granted",
        supersedes=None,
        issued_at=issued_at,
        signature=f"SIG_GRANT_{DEMO_GRANT_ID}"
    )

    doc_ref = db.collection("grants").document(event_id)
    doc_ref.set(event.model_dump())
    print(f"Seeded grant event '{event_id}'")
    print(f"  counterparty_id: {DEMO_COUNTERPARTY}")
    print(f"  work_id:         {DEMO_WORK_ID}")
    print(f"  grant_id:        {DEMO_GRANT_ID}")
    print(f"  scope:           training / open_weights / non-commercial / attribution required / US+CA")

    # Read back to verify the seed actually landed (never report unverified success)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        print("ERROR: read-back failed — document does not exist after set().", file=sys.stderr)
        sys.exit(1)
    stored = snapshot.to_dict()
    assert stored["counterparty_id"] == DEMO_COUNTERPARTY
    print("Read-back verified: document exists with expected counterparty_id.")


if __name__ == "__main__":
    seed_demo_grant()
