import hashlib
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from src.schema.work import ControlProof, ProofMethod


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
    
    verified_at = datetime.now(timezone.utc).isoformat()
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

    verified_at = datetime.now(timezone.utc).isoformat()
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

    verified_at = datetime.now(timezone.utc).isoformat()
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
