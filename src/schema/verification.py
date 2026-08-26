import hashlib
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from src.schema.work import ControlProof, ProofMethod


class UnverifiableMethodError(ValueError):
    """Raised when a control-proof method has no working verifier behind it.

    HOD-748 hardened `verify_signed_commit` and left its three siblings minting
    `status: "verified"` from non-empty arguments. Worse, none of the four was
    called from any production path at all: `POST /api/v1/works` promoted a work
    to `verified_control` whenever the request body contained a control_proof
    that merely PARSED. Three arbitrary strings bought a verified tier —
    ownership taken from attacker-controlled input, which is the same defect
    class this project already fixed twice for counterparty_id.

    A method with no verifier now refuses, and the registration route treats a
    refusal as `asserted` rather than as an error: the artist still registers,
    the claim is still recorded, and it is simply not called verified.
    """


class UnsignedCommitError(ValueError):
    """Raised when a signed-commit proof is requested for a commit that is not
    signed. A distinct type so a caller can choose to fall back to `asserted`
    deliberately, in code a reviewer can see."""


# `git log --format=%G?` codes that mean a good signature.
#   G = good, U = good but untrusted, X = good but expired,
#   Y = good, made by an expired key, R = good, made by a revoked key
# N (none), B (bad) and E (cannot check) are not proofs of anything.
_GOOD_SIGNATURE_STATUSES = frozenset({"G", "U", "X", "Y", "R"})


def _git_signature_status(commit_sha: str) -> str:
    """`git`'s own verdict on a commit's signature, or 'E' if it cannot be read."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%G?", commit_sha],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "E"
    status = out.stdout.strip()
    return status if out.returncode == 0 and status else "E"


def verify_dns_txt(
    domain: str,
    record_name: str,
    expected_token: str,
    evidence_uri: Optional[str] = None
) -> ControlProof:
    """
    Verifies ownership via DNS TXT record containing a Hodi verification token.
    """
    # Proof validation: constructs proof object if verification metadata is supplied
    if not domain or not expected_token:
        raise ValueError("DNS verification requires domain and expected_token.")
    
    raise UnverifiableMethodError(
        "dns control proofs are not verifiable by this build: nothing here performs "
        "a DNS TXT lookup, so a proof issued now would only restate the caller's "
        "own claim. Register at control_tier='asserted' until a resolver is wired.")

    verified_at = datetime.now(timezone.utc).isoformat()  # noqa: F841 - unreachable, kept for the wiring
    return ControlProof(
        method="dns",
        verified_at=verified_at,
        evidence_uri=evidence_uri or f"dns://{domain}/{record_name}",
        metadata={
            "domain": domain,
            "record_name": record_name,
            "token_hash": hashlib.sha256(expected_token.encode()).hexdigest(),
            "status": "verified"
        }
    )

def verify_well_known_file(
    target_url: str,
    expected_token: str,
    evidence_uri: Optional[str] = None
) -> ControlProof:
    """
    Verifies ownership via a well-known proof file hosted at /.well-known/hodi-proof.json or similar.
    """
    if not target_url or not expected_token:
        raise ValueError("Well-known file verification requires target_url and expected_token.")

    raise UnverifiableMethodError(
        "well_known_file control proofs are not verifiable by this build: nothing "
        "here fetches the target URL and compares the token, so a proof issued now "
        "would only restate the caller's own claim. Register at "
        "control_tier='asserted' until the fetch is wired.")

    verified_at = datetime.now(timezone.utc).isoformat()  # noqa: F841 - unreachable, kept for the wiring
    return ControlProof(
        method="well_known_file",
        verified_at=verified_at,
        evidence_uri=evidence_uri or target_url,
        metadata={
            "target_url": target_url,
            "token_hash": hashlib.sha256(expected_token.encode()).hexdigest(),
            "status": "verified"
        }
    )

def verify_signed_commit(
    repo_uri: str,
    commit_sha: str,
    author_identity: str,
    evidence_uri: Optional[str] = None
) -> ControlProof:
    """
    Verifies ownership via a GPG or SSH signed git commit.
    """
    if not repo_uri or not commit_sha:
        raise ValueError("Signed commit verification requires repo_uri and commit_sha.")

    # THIS FUNCTION USED TO VERIFY NOTHING (HOD-748).
    #
    # It checked that its arguments were non-empty and then constructed a
    # ControlProof from them. `create_work()` refuses `verified_control` without
    # a proof object, so the invariant held perfectly — over a proof that was
    # only ever a restatement of the caller's claim. The repository has
    # 0 signed commits out of 99; GitHub's API reports the referenced commit as
    # `"verified": false, "reason": "unsigned"`. The strongest ownership claim in
    # the system rested on a function whose name is a verification verb.
    #
    # It now demands an actual signature and REFUSES rather than downgrading
    # silently. A caller that cannot produce one gets an exception, not a
    # weaker proof it did not ask for — the tier is the caller's decision to
    # make explicitly, and a proof that materialises anyway is how this got here.
    status = _git_signature_status(commit_sha)
    if status not in _GOOD_SIGNATURE_STATUSES:
        raise UnsignedCommitError(
            f"commit {commit_sha[:12]} carries no good signature (git reports "
            f"{status!r}). A signed-commit control proof cannot be issued for it. "
            "Sign the commit (`git commit -S`) and retry, or register the work at "
            "control_tier='asserted', which is what the evidence supports."
        )

    verified_at = datetime.now(timezone.utc).isoformat()
    return ControlProof(
        method="signed_commit",
        verified_at=verified_at,
        evidence_uri=evidence_uri or f"{repo_uri}/commit/{commit_sha}",
        metadata={
            "repo_uri": repo_uri,
            "commit_sha": commit_sha,
            "author_identity": author_identity,
            "status": "verified"
        }
    )

def verify_platform_oauth(
    platform: str,
    account_id: str,
    account_handle: str,
    evidence_uri: Optional[str] = None
) -> ControlProof:
    """
    Verifies ownership via platform OAuth delegation (e.g. GitHub/Medium user ID token).
    """
    if not platform or not account_id:
        raise ValueError("Platform OAuth verification requires platform and account_id.")

    raise UnverifiableMethodError(
        "platform_oauth control proofs are not verifiable by this build: no OAuth "
        "token is presented, exchanged or validated here, so a proof issued now "
        "would only restate the caller's own claim. Register at "
        "control_tier='asserted' until the exchange is wired.")

    verified_at = datetime.now(timezone.utc).isoformat()  # noqa: F841 - unreachable, kept for the wiring
    return ControlProof(
        method="platform_oauth",
        verified_at=verified_at,
        evidence_uri=evidence_uri or f"oauth://{platform}/{account_handle}",
        metadata={
            "platform": platform,
            "account_id": account_id,
            "account_handle": account_handle,
            "status": "verified"
        }
    )


# --- the dispatcher production code actually calls ---------------------------

VERIFIERS = {
    "signed_commit": lambda p: verify_signed_commit(
        repo_uri=(p.get("metadata") or {}).get("repo_uri") or p.get("evidence_uri") or "",
        commit_sha=(p.get("metadata") or {}).get("commit_sha") or "",
        author_identity=(p.get("metadata") or {}).get("author_identity") or ""),
    "dns": lambda p: verify_dns_txt(
        domain=(p.get("metadata") or {}).get("domain") or "",
        record_name=(p.get("metadata") or {}).get("record_name") or "",
        expected_token=(p.get("metadata") or {}).get("expected_token") or ""),
    "well_known_file": lambda p: verify_well_known_file(
        target_url=(p.get("metadata") or {}).get("target_url") or p.get("evidence_uri") or "",
        expected_token=(p.get("metadata") or {}).get("expected_token") or ""),
    "platform_oauth": lambda p: verify_platform_oauth(
        platform=(p.get("metadata") or {}).get("platform") or "",
        account_id=(p.get("metadata") or {}).get("account_id") or "",
        account_handle=(p.get("metadata") or {}).get("account_handle") or ""),
}


def substantiate(proof: Dict[str, Any]) -> Tuple[bool, str]:
    """Can this control proof be SUBSTANTIATED, as opposed to merely parsed?

    Returns (verified, reason). Never raises for an unverifiable proof — the
    registration is still accepted, at the tier the evidence supports.

    This function is the wire that was missing. Every verifier in this module
    was reachable only from tests; the registration route decided the tier by
    asking whether the caller's `control_proof` field was non-empty and parsed.
    """
    method = (proof or {}).get("method")
    verifier = VERIFIERS.get(method)
    if verifier is None:
        return False, (f"Unknown control-proof method {method!r}; ownership is ASSERTED, "
                       "not verified.")
    try:
        verifier(proof)
    except UnverifiableMethodError as exc:
        return False, f"Ownership is ASSERTED, not verified: {exc}"
    except UnsignedCommitError as exc:
        return False, f"Ownership is ASSERTED, not verified: {exc}"
    except Exception as exc:  # malformed metadata for an otherwise-wired method
        return False, (f"Ownership is ASSERTED, not verified: the {method} proof could not "
                       f"be checked ({exc}).")
    return True, f"Control proof VERIFIED by {method}."
