"""
src/schema/signing.py — the one place that produces a `signature` value, and the
one place that states what it is worth (HOD-350).

Hodi issues revocation notices, receipts and grant events carrying a
`signature` field. **None of those values are cryptographic signatures.** They
were literals — `SIG_REVOKED`, `SIG_RECEIPT`, `SIG_REVOCATION_<grant_id>` —
while the README described "a dated signed notice" and the demo narration said
"signed notices and receipts are issued". Nothing anywhere verified them,
because there is nothing to verify: the string is derived from the document's
own identifiers and any party could produce it.

That is the exact overclaim shape this project exists to refuse — a stated
property, a field that looks like the mechanism, and nothing connecting them —
so the value now says what it is, in every dump, on camera included.

WHY NOT JUST SIGN THEM. A signature is only worth something if the recipient can
verify it without being able to forge it. HMAC with a service-held secret cannot
do that: a counterparty who can verify a notice can mint one. Doing this
properly needs asymmetric signing with a published key — Cloud KMS or a managed
Ed25519 key, plus key distribution, rotation and a verification endpoint. That
is a real feature, not a rename, and shipping symmetric signing to make the
field look cryptographic would be worse than the placeholder: it would be
security theatre over a legal artifact.

So: the placeholder is honest and labelled, the limit is disclosed in the
README's "What Hodi will not claim", and `tests/test_signature_honesty.py`
fails if any code path emits a value that looks like a real signature.
"""

PLACEHOLDER_PREFIX = "UNSIGNED_PLACEHOLDER"

SIGNATURE_CLAIM_LIMIT = (
    "Not a cryptographic signature. This value is a labelled placeholder derived "
    "from the document's own identifiers; it proves nothing and is verified by "
    "nothing. Verifiable signing requires an asymmetric key the recipient can "
    "check without being able to forge — see docs/FINDINGS.md."
)


def unsigned_placeholder(kind: str, reference: str) -> str:
    """
    The only sanctioned way to fill a `signature` field.

    `kind` names the document class (grant, revoked, receipt, revocation_receipt)
    and `reference` its identifier, so a reader can tell which document the value
    belongs to — and, from the prefix, that it is not a signature.
    """
    return f"{PLACEHOLDER_PREFIX}:{kind}:{reference}"


def is_unsigned_placeholder(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX + ":")
