"""
src/schema/signing.py — the one place that produces a `signature` value, and the
one place that states what it is worth (HOD-350, HOD-706).

HISTORY, kept because it is the point. Hodi's notices, receipts and grant
events carry a `signature` field, and for most of this project's life none of
those values were cryptographic signatures — first hand-typed literals
(`SIG_REVOKED`), then, from 2026-08-12, honest labelled placeholders
(`UNSIGNED_PLACEHOLDER:<kind>:<id>`), because HMAC would have been worse than
the placeholder: a shared secret makes a notice verifiable only by parties who
could equally forge it, which over a legal artifact is security theatre.

WHAT EXISTS NOW (HOD-706): real asymmetric signing, in exactly the shape the
placeholder's own docstring demanded —

  * `KmsSigner` — Cloud KMS asymmetric signing (ECDSA P-256/SHA-256) for the
    DEPLOYED path. The private key never leaves KMS; the runtime identity holds
    only `cloudkms.signer`; recipients verify against the published public key
    (`/verification-key`, and committed after `scripts/setup_kms_signing.sh`).
  * `EphemeralEd25519Signer` — an in-process Ed25519 key for the CREDENTIAL-FREE
    demo and the offline suite. Explicitly labelled `ED25519-EPHEMERAL` in every
    envelope: it proves the mechanism (canonicalize → hash → sign → verify →
    tamper detection) and deliberately does NOT claim durable authority, because
    the key dies with the process and its public key is only as trustworthy as
    the run that printed it.
  * The PLACEHOLDER — retained verbatim for every path where no signer is
    configured, and for reading history: documents written before signing
    existed still say `UNSIGNED_PLACEHOLDER`/`SIG_REVOKED` and cannot be
    rewritten (the log is append-only; the runtime identity holds no update).

The rule, unchanged in spirit: a `signature` field carries either a VERIFIABLE
envelope or a value that SAYS it proves nothing. Nothing in between —
`tests/test_signature_honesty.py` fails on any path that emits a
signature-looking string nothing can verify.
"""

import base64
import json
import os
from typing import Any, Dict, Optional, Tuple

PLACEHOLDER_PREFIX = "UNSIGNED_PLACEHOLDER"

SIGNATURE_CLAIM_LIMIT = (
    "Not a cryptographic signature. This value is a labelled placeholder derived "
    "from the document's own identifiers; it proves nothing and is verified by "
    "nothing. Verifiable signing requires an asymmetric key the recipient can "
    "check without being able to forge — see docs/FINDINGS.md."
)

# Envelope format: "<ALG>:<key_id>:<base64(signature_bytes)>"
# ALG ∈ {ED25519-EPHEMERAL, KMS-ECDSA-P256-SHA256}. The alg tag states the
# authority class out loud: EPHEMERAL can never be mistaken for the KMS key.
ENVELOPE_ALGS = ("ED25519-EPHEMERAL", "KMS-ECDSA-P256-SHA256")


def unsigned_placeholder(kind: str, reference: str) -> str:
    """
    The sanctioned `signature` value when NO signer is configured.

    `kind` names the document class (grant, revoked, receipt, revocation_receipt)
    and `reference` its identifier, so a reader can tell which document the value
    belongs to — and, from the prefix, that it is not a signature.
    """
    return f"{PLACEHOLDER_PREFIX}:{kind}:{reference}"


def is_unsigned_placeholder(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX + ":")


def is_signature_envelope(value: str) -> bool:
    return isinstance(value, str) and any(value.startswith(alg + ":") for alg in ENVELOPE_ALGS)


def parse_envelope(value: str) -> Tuple[str, str, bytes]:
    """Returns (alg, key_id, signature_bytes); raises ValueError on anything else."""
    if not is_signature_envelope(value):
        raise ValueError(f"Not a signature envelope: {value[:40]!r}")
    alg, key_id, b64 = value.split(":", 2)
    return alg, key_id, base64.b64decode(b64)


def canonical_json_bytes(doc: Dict[str, Any]) -> bytes:
    """
    The byte representation everything signs and verifies: JSON with sorted
    keys, minimal separators, UTF-8. One canonicalization, defined once —
    signer and verifier that canonicalize differently agree on nothing.
    """
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def signable_bytes(model_dump: Dict[str, Any], exclude: Tuple[str, ...] = ("signature",)) -> bytes:
    """Canonical bytes of a document WITHOUT its signature field(s) — what the
    signature is over. `model_dump` must be JSON-mode (strings, not datetimes)."""
    doc = {k: v for k, v in model_dump.items() if k not in exclude}
    return canonical_json_bytes(doc)


class EphemeralEd25519Signer:
    """
    In-process Ed25519 signer for the credential-free demo and tests.

    LABELLED EPHEMERAL in every envelope, on purpose: the key is generated at
    construction, dies with the process, and its public key carries no
    authority beyond the run that printed it. It exists to make the MECHANISM
    demonstrable offline — a tampered byte fails, an untampered document
    verifies — never to impersonate the production key.
    """

    ALG = "ED25519-EPHEMERAL"

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        self._private = Ed25519PrivateKey.generate()
        raw_pub = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.key_id = "ephemeral-" + raw_pub[:4].hex()
        self.public_key_pem = self._private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")

    def sign(self, payload: bytes) -> str:
        sig = self._private.sign(payload)
        return f"{self.ALG}:{self.key_id}:{base64.b64encode(sig).decode('ascii')}"


class KmsSigner:
    """
    Cloud KMS asymmetric signing (HOD-706, live path). Requires:
      * `scripts/setup_kms_signing.sh` run once (creates the keyring/key and
        grants roles/cloudkms.signer to the runtime SA ONLY),
      * HODI_KMS_KEY_VERSION set to the full resource name
        projects/.../cryptoKeyVersions/N.
    The private key never leaves KMS; this class holds no secret. Lazy import
    so the credential-free paths never need google-cloud-kms at all.
    """

    ALG = "KMS-ECDSA-P256-SHA256"

    def __init__(self, key_version_name: Optional[str] = None):
        self.key_version_name = key_version_name or os.environ.get("HODI_KMS_KEY_VERSION", "")
        if not self.key_version_name:
            raise RuntimeError("KmsSigner needs HODI_KMS_KEY_VERSION (full cryptoKeyVersions resource name).")
        from google.cloud import kms
        self._client = kms.KeyManagementServiceClient()
        self.key_id = self.key_version_name.rsplit("cryptoKeys/", 1)[-1]

    def sign(self, payload: bytes) -> str:
        import hashlib
        digest = hashlib.sha256(payload).digest()
        response = self._client.asymmetric_sign(
            request={"name": self.key_version_name, "digest": {"sha256": digest}})
        return f"{self.ALG}:{self.key_id}:{base64.b64encode(response.signature).decode('ascii')}"

    def public_key_pem(self) -> str:
        return self._client.get_public_key(request={"name": self.key_version_name}).pem


def verify_envelope(envelope: str, payload: bytes, public_key_pem: str) -> bool:
    """
    True iff `envelope` is a valid signature over `payload` under the given
    public key. Verification needs ONLY the public key — the property the
    placeholder era was missing: the recipient can check what they could
    never mint.
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature

    alg, _key_id, sig = parse_envelope(envelope)
    key = load_pem_public_key(public_key_pem.encode("ascii"))
    try:
        if alg == "ED25519-EPHEMERAL":
            if not isinstance(key, Ed25519PublicKey):
                return False
            key.verify(sig, payload)
        elif alg == "KMS-ECDSA-P256-SHA256":
            key.verify(sig, payload, ec.ECDSA(hashes.SHA256()))
        else:
            return False
        return True
    except InvalidSignature:
        return False


_active_signer = None


def get_active_signer():
    """
    The signer this process signs with, or None (→ placeholders).

    Selection is explicit, never guessed: HODI_SIGNING=kms uses Cloud KMS
    (deployed path, after setup); HODI_SIGNING=ephemeral uses the in-process
    labelled key (demo, tests); unset/anything else means NO signer, and
    every signature field stays an honest placeholder — exactly the
    pre-HOD-706 behavior.
    """
    global _active_signer
    mode = os.environ.get("HODI_SIGNING", "").lower()
    if mode == "kms":
        if _active_signer is None or not isinstance(_active_signer, KmsSigner):
            _active_signer = KmsSigner()
        return _active_signer
    if mode == "ephemeral":
        if _active_signer is None or not isinstance(_active_signer, EphemeralEd25519Signer):
            _active_signer = EphemeralEd25519Signer()
        return _active_signer
    return None


def signature_for(kind: str, reference: str, payload: bytes) -> str:
    """
    THE entry point for filling a `signature` field: a verifiable envelope
    when a signer is configured, the labelled placeholder when not. Nothing
    in between.
    """
    signer = get_active_signer()
    if signer is None:
        return unsigned_placeholder(kind, reference)
    return signer.sign(payload)


def sign_pydantic(model, kind: str, reference: str):
    """
    Returns a copy of `model` whose `signature` field is signature_for() over
    the document's canonical bytes WITHOUT the signature field. Whatever value
    `signature` held while building the model is irrelevant — it is excluded
    from the signed payload and replaced in the copy.
    """
    payload = signable_bytes(model.model_dump(mode="json"))
    return model.model_copy(update={"signature": signature_for(kind, reference, payload)})


def verify_document(doc: Dict[str, Any], public_key_pem: str) -> bool:
    """
    Verifies a signed document dict (JSON-mode values): recomputes the
    canonical bytes without `signature` and checks the envelope. False for
    placeholders and for anything tampered — a single changed byte anywhere
    in the document changes the canonical bytes.
    """
    envelope = doc.get("signature", "")
    if not is_signature_envelope(envelope):
        return False
    return verify_envelope(envelope, signable_bytes(doc), public_key_pem)
