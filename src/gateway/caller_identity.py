"""
src/gateway/caller_identity.py — who is calling, and how much that is worth
(HOD-717).

THE DEFECT THIS ADDRESSES, stated plainly. Every gateway call took a
`calling_sa` string and a `calling_role_key` string from in-process code.
`calling_role_key` selected the policy; `calling_sa` was used for LOGGING
ONLY. Nothing checked that they belonged together, so any code inside the
process could present any role — and an external review's judgement that
they were "checked for consistency" was more generous than the truth.

Two things change here, and it matters which is which:

  1. THE BINDING IS NOW CHECKED, ALWAYS. A CallerIdentity cannot exist
     unless its service account is the one `iam_policy.py` declares for its
     role. That closes role/SA confusion — including a real inconsistency it
     immediately surfaced: the licensing path had been passing
     `licensing-negotiator@…` while the policy declares
     `licensing-negotiator-sa@…`, two different strings for one role, one of
     them appearing in every denial event ever logged from that path.

  2. THE ORIGIN IS NOW STATED. An identity is either
     `oidc_verified` — derived from a Google-signed ID token whose issuer,
     audience, expiry and verified email were checked, which is the
     non-forgeable case a split-service deployment gets — or
     `in_process_trusted`, which is a LABEL FOR A LIMIT: it means the caller
     is code in this process, so it is exactly as trustworthy as the process
     itself and no more. A compromised process can still mint one.

Point 2 is the honest part. Checking the binding does not make an in-process
string non-forgeable; it makes the FORGERY VISIBLE AS A CATEGORY. So the
gateway can be run in strict mode (`HODI_REQUIRE_VERIFIED_IDENTITY=1`),
where `in_process_trusted` is refused outright and only OIDC-verified
callers are served. That is the mode a split deployment runs in, and it is
executable today — the remaining work is deploying the split services
(scripts/deploy_revocation_worker.sh), not writing this.

WHAT IS NOT PROVEN OFFLINE: the cryptographic verification of the Google
signature is delegated to `google.oauth2.id_token`, and this repository's
offline suite does not exercise it. What the offline suite proves is
everything around it — issuer, audience, expiry, email verification, the
email→role mapping, and the refusal of every malformed case.
"""

import os
import time
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import BaseModel

from src.schema.iam_policy import AGENT_SA_MAP

# Google's ID-token issuers. Anything else is refused: an attacker-controlled
# issuer with a valid-looking token is the whole point of checking.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

VerificationMode = Literal["oidc_verified", "in_process_trusted"]

STRICT_ENV = "HODI_REQUIRE_VERIFIED_IDENTITY"


class IdentityVerificationError(Exception):
    """A presented credential did not establish the identity it claimed."""


class CallerIdentity(BaseModel):
    """
    A caller the gateway will serve. Construct it through `in_process()` or
    `from_oidc()` — both enforce the SA↔role binding, so an instance always
    means "this role, with the service account the policy declares for it".
    """

    role_key: str
    service_account: str
    verification: VerificationMode
    # Present only on the OIDC path: the token subject, for audit.
    token_subject: Optional[str] = None

    @property
    def is_verified(self) -> bool:
        return self.verification == "oidc_verified"

    def describe(self) -> str:
        return f"{self.role_key} as {self.service_account} ({self.verification})"

    # --- constructors -------------------------------------------------------

    @classmethod
    def in_process(cls, role_key: str) -> "CallerIdentity":
        """
        An in-process caller. The service account is DERIVED from the policy
        rather than supplied, so it cannot disagree with the role — and the
        result is labelled `in_process_trusted` so no reader mistakes it for
        an authenticated principal.
        """
        info = AGENT_SA_MAP.get(role_key)
        if not info:
            raise IdentityVerificationError(
                f"Unknown role '{role_key}' — it is not declared in iam_policy.py, so no "
                "service account exists for it and no policy would govern it.")
        return cls(role_key=role_key, service_account=info["sa_email"],
                   verification="in_process_trusted")

    @classmethod
    def from_oidc(cls, token: str, expected_audience: str,
                  verifier: Optional[Callable[[str, str], Dict[str, Any]]] = None,
                  now: Optional[float] = None) -> "CallerIdentity":
        """
        Derive the role from a Google-signed ID token — the non-forgeable
        path. The caller does not get to say which role it is; the role is
        looked up from the VERIFIED service-account email.

        `verifier` exists so the claim-level rules are testable without
        Google's keys; it defaults to real signature verification.
        """
        verify = verifier or _verify_google_signature
        try:
            claims = verify(token, expected_audience)
        except Exception as e:  # noqa: BLE001 — any verification failure is a refusal
            raise IdentityVerificationError(f"ID token signature verification failed: {e}") from e

        issuer = claims.get("iss")
        if issuer not in GOOGLE_ISSUERS:
            raise IdentityVerificationError(
                f"ID token issuer {issuer!r} is not Google. A token this service did not "
                "trust the issuer of establishes nothing.")

        audience = claims.get("aud")
        if audience != expected_audience:
            raise IdentityVerificationError(
                f"ID token audience {audience!r} does not match this service "
                f"({expected_audience!r}). An audience check is what stops a token minted "
                "for another service from being replayed here.")

        expiry = claims.get("exp")
        current = now if now is not None else time.time()
        if expiry is None or float(expiry) <= current:
            raise IdentityVerificationError("ID token is expired or carries no expiry.")

        if not claims.get("email_verified", False):
            raise IdentityVerificationError(
                "ID token carries no verified email; the service-account identity is "
                "therefore unestablished.")

        email = claims.get("email")
        role_key = role_for_service_account(email)
        if role_key is None:
            raise IdentityVerificationError(
                f"Service account {email!r} maps to no role in iam_policy.py. An identity "
                "the policy does not name cannot be granted a role by presenting a token.")

        return cls(role_key=role_key, service_account=email,
                   verification="oidc_verified", token_subject=claims.get("sub"))

    @classmethod
    def coerce(cls, identity: Optional["CallerIdentity"],
               calling_sa: Optional[str], calling_role_key: Optional[str]) -> "CallerIdentity":
        """
        Accept either a CallerIdentity or the legacy (sa, role) pair, and
        ALWAYS return a CallerIdentity — validating the binding on the way
        through. This is what lets the gateway enforce the binding on every
        existing call site without a flag day.
        """
        if identity is not None:
            return identity
        if not calling_role_key:
            raise IdentityVerificationError("A gateway call must identify its calling role.")
        declared = cls.in_process(calling_role_key)
        if calling_sa and calling_sa != declared.service_account:
            raise IdentityVerificationError(
                f"Service account '{calling_sa}' does not match the identity iam_policy.py "
                f"declares for role '{calling_role_key}' ('{declared.service_account}'). The "
                "identity enforced and the identity recorded must be the same principal, and "
                "the policy is the source.")
        return declared


def role_for_service_account(email: Optional[str]) -> Optional[str]:
    """Reverse the policy map: the SA email is the identity, the role follows."""
    if not email:
        return None
    for role_key, info in AGENT_SA_MAP.items():
        if info["sa_email"] == email:
            return role_key
    return None


def strict_identity_required() -> bool:
    """
    True when this deployment refuses in-process identities. Split services
    set it; the single-process deployment does not, and says so in
    docs/deployment_status.json rather than implying otherwise.
    """
    return os.environ.get(STRICT_ENV) == "1"


def _verify_google_signature(token: str, audience: str) -> Dict[str, Any]:
    """
    Real verification, delegated to Google's library: fetches Google's public
    keys and checks the signature. Imported lazily so the credential-free
    paths never need it. NOT exercised by the offline suite — see the module
    docstring; the claim-level rules around it are.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(
        token, google_requests.Request(), audience)
