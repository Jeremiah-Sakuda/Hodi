"""Private Cloud Run client for the revocation workload (HOD-711).

The front door authenticates the artist and verifies work ownership.  The
revocation workload, running as ``revocation-propagator-sa``, is the only
process that folds grants and appends revocation effects in production.
"""

import json
import urllib.error
import urllib.request
from typing import Optional

from src.agents.revocation_propagator import CascadeResult


REVOCATION_CALL_TIMEOUT_SECONDS = 120.0


class RevocationWorkerUnavailable(RuntimeError):
    """The private worker could not be reached or returned an invalid result."""


def _id_token(audience: str) -> str:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.fetch_id_token(google_requests.Request(), audience)


def execute_revocation(
    worker_url: str,
    *,
    work_id: str,
    revoked_use_type: str,
    operation_id: Optional[str],
) -> CascadeResult:
    """Invoke the private worker and require its execution-surface attestation."""
    payload = json.dumps({
        "work_id": work_id,
        "revoked_use_type": revoked_use_type,
        "operation_id": operation_id,
    }).encode("utf-8")
    try:
        token = _id_token(worker_url)
        request = urllib.request.Request(
            worker_url.rstrip("/") + "/internal/revocation/execute",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(
            request, timeout=REVOCATION_CALL_TIMEOUT_SECONDS
        ) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RevocationWorkerUnavailable(
            f"private revocation worker refused with HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - boundary normalizes transport failures
        raise RevocationWorkerUnavailable(
            f"private revocation worker failed: {type(exc).__name__}: {exc}"
        ) from exc

    if body.get("execution_surface") != "private-revocation-worker":
        raise RevocationWorkerUnavailable(
            "private revocation worker response omitted its execution-surface attestation"
        )
    try:
        return CascadeResult(**body["result"])
    except Exception as exc:  # noqa: BLE001 - malformed remote data must fail closed
        raise RevocationWorkerUnavailable(
            f"private revocation worker returned an invalid cascade: {exc}"
        ) from exc
