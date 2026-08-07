"""
src/api/auth.py — signed buyer request authentication (HOD-360, HOD-311).

THE RULE: a counterparty's identity is derived from a VERIFIED CREDENTIAL,
never from a field in the request body.

The original buyer API took `counterparty_id` from the request body and used it
BOTH as the query filter and as the "session context" the gateway checked the
filter against — so the gateway compared the caller's claim against itself and
any anonymous caller could read any counterparty's grants. The signature field
was only tested for truthiness. See BUILD-LOG 2026-08-07 (correction #4).

Each counterparty holds a shared secret registered under a `key_id`. A request
carries three headers — `X-Hodi-Key-Id`, `X-Hodi-Timestamp`, `X-Hodi-Signature`
— where the signature is HMAC-SHA256 over

    key_id \n timestamp \n sha256(RAW REQUEST BODY BYTES)

Signing the raw bytes (rather than a re-serialization of the parsed model)
means the client and server never have to agree on how a Pydantic model
round-trips through JSON — the signature covers exactly what was sent, so any
tampering anywhere in the body invalidates it.

The server recomputes the HMAC with the secret bound to that `key_id`; the
authenticated `counterparty_id` is the one stored ON THE CREDENTIAL RECORD.
The body's `counterparty_id`, if present, is only ever compared — never trusted.
"""

import os
import json
import hmac
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel

CREDENTIAL_COLLECTION = "counterparty_credentials"
# A signature older than this is refused, so a captured request cannot be
# replayed indefinitely.
MAX_CLOCK_SKEW_SECONDS = 300

HEADER_KEY_ID = "X-Hodi-Key-Id"
HEADER_TIMESTAMP = "X-Hodi-Timestamp"
HEADER_SIGNATURE = "X-Hodi-Signature"


class AuthenticatedCounterparty(BaseModel):
    counterparty_id: str
    key_id: str


class RequestAuthenticationError(Exception):
    """Raised when a request cannot be authenticated. Carries a reason suitable
    for a structured denial event; never leaks whether a key_id exists."""


def compute_signature(secret: str, key_id: str, issued_at: str, body: bytes) -> str:
    """HMAC-SHA256 over key_id, timestamp, and a digest of the RAW body bytes."""
    body_digest = hashlib.sha256(body).hexdigest()
    message = f"{key_id}\n{issued_at}\n{body_digest}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class CredentialStore:
    """Firestore-backed credential lookup. Injectable so tests never need the
    production collection (and so no test backdoor exists in this module)."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        self._db = None

    def _client(self):
        if self._db is None:
            from google.cloud import firestore
            try:
                self._db = firestore.Client(project=self.project_id)
            except Exception:
                token = subprocess.check_output(
                    ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
                ).decode("utf-8").strip()
                from google.oauth2 import credentials as oauth2_credentials
                self._db = firestore.Client(
                    project=self.project_id,
                    credentials=oauth2_credentials.Credentials(token)
                )
        return self._db

    def get(self, key_id: str) -> Optional[Dict[str, Any]]:
        snapshot = self._client().collection(CREDENTIAL_COLLECTION).document(key_id).get()
        return snapshot.to_dict() if snapshot.exists else None


class InMemoryCredentialStore:
    """For tests and offline runs."""

    def __init__(self, credentials: Dict[str, Dict[str, Any]]):
        self._credentials = credentials

    def get(self, key_id: str) -> Optional[Dict[str, Any]]:
        return self._credentials.get(key_id)


def authenticate(
    key_id: str,
    issued_at: str,
    signature: str,
    body: bytes,
    store: Any,
    now: Optional[datetime] = None,
) -> AuthenticatedCounterparty:
    """
    Returns the AUTHENTICATED counterparty, or raises RequestAuthenticationError.
    There is no third outcome and no unauthenticated path to grant data.
    """
    if not key_id or not signature or not issued_at:
        raise RequestAuthenticationError("Request must carry key_id, issued_at, and signature.")

    try:
        issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    except ValueError:
        raise RequestAuthenticationError("issued_at is not a valid ISO-8601 timestamp.")
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)

    reference = now or datetime.now(timezone.utc)
    if abs((reference - issued).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
        raise RequestAuthenticationError(
            f"Request timestamp is outside the {MAX_CLOCK_SKEW_SECONDS}s freshness window."
        )

    record = store.get(key_id)
    # Uniform failure text: an attacker must not be able to enumerate valid
    # key_ids by comparing "unknown key" against "bad signature".
    if not record or not record.get("active", True) or not record.get("secret"):
        raise RequestAuthenticationError("Signature verification failed.")

    expected = compute_signature(record["secret"], key_id, issued_at, body)
    if not hmac.compare_digest(expected, signature):
        raise RequestAuthenticationError("Signature verification failed.")

    counterparty_id = record.get("counterparty_id")
    if not counterparty_id:
        raise RequestAuthenticationError("Credential record carries no counterparty binding.")

    return AuthenticatedCounterparty(counterparty_id=counterparty_id, key_id=key_id)
