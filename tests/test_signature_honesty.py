"""
tests/test_signature_honesty.py — a `signature` field must not pretend to be one
(HOD-350, HOD-620).

Hodi's revocation notices, receipts and grant events carry a `signature`. None
of them are cryptographic signatures, and **nothing in the codebase verifies
one** — the values were literals (`SIG_REVOKED`, `SIG_RECEIPT`,
`SIG_REVOCATION_<grant_id>`) derived from the document's own identifiers, while
the README described "a dated signed notice" and the demo narration said "signed
notices and receipts are issued".

That is the ledger's signature failure shape applied to a legal artifact: a
stated property, a field named after the mechanism, and nothing connecting them.
The fix is not to fake a signature — HMAC with a service-held secret is
verifiable only by parties who could also forge it — but to label the value
honestly and disclose the limit. See src/schema/signing.py.

These tests fail if any runtime path emits a value that *looks* like a real
signature, or if the outward disclosure disappears.
"""

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.schema.signing import (
    PLACEHOLDER_PREFIX, SIGNATURE_CLAIM_LIMIT,
    is_unsigned_placeholder, unsigned_placeholder,
)

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIRS = [ROOT / "src", ROOT / "scripts"]

# A `signature=` keyword argument (Pydantic field) assigned a string literal.
# Deliberately lowercase-and-boundary-anchored so it matches the model field and
# NOT `HEADER_SIGNATURE = "X-Hodi-Signature"`, which names an HTTP header — a
# different concept, and one that carries a genuine HMAC.
FAKE_SIGNATURE_LITERALS = re.compile(
    r'(?<![A-Za-z_])signature\s*=\s*(?:f?["\'])(?!.*\{)(?P<value>[^"\']*)["\']')


def runtime_python_files():
    for base in RUNTIME_DIRS:
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


class PlaceholderHelperTest(unittest.TestCase):

    def test_placeholder_is_self_describing(self):
        value = unsigned_placeholder("receipt", "grant-x")
        self.assertTrue(value.startswith(PLACEHOLDER_PREFIX + ":"))
        self.assertIn("grant-x", value)
        self.assertTrue(is_unsigned_placeholder(value))

    def test_a_real_looking_value_is_not_mistaken_for_a_placeholder(self):
        for impostor in ("SIG_REVOKED", "SIG_RECEIPT", "a3f9c1e2", ""):
            self.assertFalse(is_unsigned_placeholder(impostor))


class NoHandWrittenSignatureLiteralsTest(unittest.TestCase):
    """
    The guard that actually bites: no runtime file may assign a *string literal*
    to a `signature=` field. Every value must come from unsigned_placeholder(),
    so the honest prefix cannot be bypassed by typing a new `SIG_...` constant.

    Exempted by construction: `signature=request.headers.get(...)` and other
    non-literal expressions, which this pattern does not match.
    """

    def test_no_runtime_file_assigns_a_signature_string_literal(self):
        offenders = []
        for path in runtime_python_files():
            if path.name == "signing.py":
                continue  # defines the prefix; contains no assignments
            for line_no, line in enumerate(path.read_text().splitlines(), 1):
                m = FAKE_SIGNATURE_LITERALS.search(line)
                if m and not is_unsigned_placeholder(m.group("value")):
                    offenders.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "signature fields must be filled by unsigned_placeholder(), never a "
            "hand-written literal that reads as a real signature:\n  "
            + "\n  ".join(offenders))


class EmittedDocumentsAreLabelledTest(unittest.TestCase):
    """End-to-end: the documents a counterparty actually receives say so."""

    def setUp(self):
        import os
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

    def test_revocation_receipt_signature_is_labelled(self):
        from src.gateway.gateway import AgentGateway
        from src.schema.revocation import RevocationNotice
        notice = RevocationNotice(
            grant_id="grant-x", counterparty_id="cp-1",
            revoked_at=datetime.now(timezone.utc), notice_text="terminated; does not un-train")
        receipt = AgentGateway().deliver_revocation_notice(
            sender="revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
            counterparty_id="cp-1", notice=notice)
        self.assertTrue(is_unsigned_placeholder(receipt.signature),
                        f"receipt signature is not labelled: {receipt.signature!r}")

    def test_revoked_grant_events_are_labelled(self):
        from src.agents.revocation_propagator import RevocationPropagatorAgent
        from src.gateway.gateway import AgentGateway
        from src.schema.grant_event import GrantEvent
        from src.schema.scope import Scope
        t = datetime(2026, 8, 1, tzinfo=timezone.utc)
        scope = Scope(use_type="training", model_class="all_models", commercial=True,
                      attribution_required=False, territory=[], valid_from=t, valid_until=None)
        events = [GrantEvent(event_id="e1", grant_id="g1", work_id="w1", counterparty_id="cp-1",
                             scope=scope, kind="granted", issued_at=t,
                             signature=unsigned_placeholder("grant", "g1"))]
        agent = RevocationPropagatorAgent(gateway=AgentGateway(), memory_bank_events=events)
        result = agent.execute_revocation_cascade(work_id="w1", revoked_use_type="training")
        self.assertEqual(len(result.affected_grants), 1)
        revoked = [e for e in events if e.kind == "revoked"]
        self.assertTrue(revoked, "cascade appended no revoked event to the in-memory log")
        for event in revoked:
            self.assertTrue(is_unsigned_placeholder(event.signature),
                            f"revoked event signature is not labelled: {event.signature!r}")


class DisclosureIsPublishedTest(unittest.TestCase):
    """The limit is only honest if a reader is told. If the README bullet is
    removed, this fails rather than letting the claim quietly revert."""

    def test_readme_discloses_that_signatures_are_placeholders(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(
            readme, r"(?i)not a cryptographic signature|signature fields are (labelled )?placeholders",
            "README must disclose that `signature` fields are placeholders")

    def test_the_claim_limit_names_the_missing_property(self):
        self.assertIn("asymmetric", SIGNATURE_CLAIM_LIMIT.lower())
        self.assertIn("verif", SIGNATURE_CLAIM_LIMIT.lower())


if __name__ == "__main__":
    unittest.main()
