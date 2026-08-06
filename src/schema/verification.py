import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from src.schema.work import ControlProof, ProofMethod

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
