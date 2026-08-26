"""
Cryptographic provenance (HOD-706).

The property under test: a receipt can be verified by a party that could
not have forged it — and a single tampered byte fails verification.

Three modes, each honest about what it is:
  * no signer configured  → the labelled placeholder, exactly as before;
  * HODI_SIGNING=ephemeral → a real Ed25519 signature under a key whose
    envelope SAYS it is ephemeral (mechanism, not durable authority);
  * HODI_SIGNING=kms       → Cloud KMS (live-path only; constructing the
    signer without the env/credentials raises, asserted here).

Verification uses ONLY the public key — the exact property the placeholder
era was missing and HMAC could never provide.
"""

import os
import unittest
from datetime import datetime, timezone

from src.schema.grant_event import Receipt
from src.schema import signing
from src.schema.signing import (
    EphemeralEd25519Signer, KmsSigner,
    canonical_json_bytes, signable_bytes, sign_pydantic, signature_for,
    is_signature_envelope, is_unsigned_placeholder, parse_envelope,
    verify_envelope, verify_document,
)
from tests.offline_env import force_offline

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _receipt(**overrides) -> Receipt:
    fields = dict(receipt_id="r-1", grant_id="g-1", work_id="w-1",
                  counterparty_id="cp-1", payload_hash="ab" * 32,
                  issued_at=NOW, signature="")
    fields.update(overrides)
    return Receipt(**fields)


class TestCanonicalization(unittest.TestCase):
    def test_canonical_bytes_are_key_order_independent(self):
        a = canonical_json_bytes({"b": 1, "a": [1, 2]})
        b = canonical_json_bytes({"a": [1, 2], "b": 1})
        self.assertEqual(a, b)

    def test_signable_bytes_exclude_the_signature_field(self):
        doc = {"x": 1, "signature": "anything"}
        self.assertEqual(signable_bytes(doc), canonical_json_bytes({"x": 1}))

    def test_any_value_change_changes_the_bytes(self):
        base = signable_bytes(_receipt().model_dump(mode="json"))
        changed = signable_bytes(_receipt(grant_id="g-2").model_dump(mode="json"))
        self.assertNotEqual(base, changed)


class TestEphemeralSigning(unittest.TestCase):
    def setUp(self):
        self.signer = EphemeralEd25519Signer()

    def test_round_trip_verifies_with_only_the_public_key(self):
        payload = b"the exact bytes"
        envelope = self.signer.sign(payload)
        self.assertTrue(is_signature_envelope(envelope))
        alg, key_id, _ = parse_envelope(envelope)
        self.assertEqual(alg, "ED25519-EPHEMERAL")
        self.assertEqual(key_id, self.signer.key_id)
        self.assertTrue(verify_envelope(envelope, payload, self.signer.public_key_pem))

    def test_one_tampered_byte_fails_verification(self):
        payload = bytearray(b"the exact bytes")
        envelope = self.signer.sign(bytes(payload))
        payload[3] ^= 0x01
        self.assertFalse(verify_envelope(envelope, bytes(payload), self.signer.public_key_pem))

    def test_a_different_key_fails_verification(self):
        envelope = self.signer.sign(b"payload")
        other = EphemeralEd25519Signer()
        self.assertFalse(verify_envelope(envelope, b"payload", other.public_key_pem))

    def test_the_envelope_says_it_is_ephemeral(self):
        """The alg tag is the honesty label: a demo signature can never be
        mistaken for the production KMS key's."""
        self.assertTrue(self.signer.sign(b"x").startswith("ED25519-EPHEMERAL:"))


class TestSignedDocuments(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_SIGNING"] = "ephemeral"
        signing._active_signer = None
        self.addCleanup(lambda: (os.environ.pop("HODI_SIGNING", None),
                                 setattr(signing, "_active_signer", None)))

    def test_a_document_verifies_in_the_form_FIRESTORE_SERVES_IT(self):
        """The signature must survive the round trip through storage (HOD-749).

        Pydantic's JSON mode renders UTC as `...T12:00:00Z`. A document read
        back out of Firestore carries real datetime objects, and re-serialising
        those gives `...T12:00:00+00:00`. Same instant, different bytes,
        different canonical JSON — so the signature verified over what was
        signed and FAILED over the document as served. A third party following
        the published procedure against a stored grant got "signature invalid"
        on an untampered document, which is indistinguishable from tampering.

        Every test passed because inline receipts never left the process and so
        never acquired the second spelling. This one applies it deliberately.
        """
        from datetime import datetime, timezone
        from src.schema.grant_event import GrantEvent
        from src.schema.scope import Scope

        at = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        event = sign_pydantic(GrantEvent(
            event_id="e-served", grant_id="g-served", work_id="w-served",
            counterparty_id="buyer-served", kind="granted", issued_at=at, signature="x",
            scope=Scope(use_type="training", model_class="all_models",
                        attribution_required=False, commercial=True, valid_from=at),
        ), kind="grant", reference="g-served")
        pem = signing.get_active_signer().public_key_pem

        as_signed = event.model_dump(mode="json")
        self.assertTrue(verify_document(as_signed, pem))

        # The same document as Firestore hands it back: '+00:00', not 'Z'.
        as_served = dict(as_signed)
        as_served["issued_at"] = at.isoformat()
        as_served["scope"] = dict(as_signed["scope"], valid_from=at.isoformat())
        self.assertNotEqual(as_served["issued_at"], as_signed["issued_at"],
                            "fixture is wrong: both spellings are identical, so this "
                            "test would pass without exercising anything")
        self.assertTrue(
            verify_document(as_served, pem),
            "an untampered stored document failed verification purely because its "
            "timestamps came back spelled differently")

    def test_normalising_timestamps_does_not_blunt_tamper_detection(self):
        """The obvious way to break the fix above: normalise so aggressively
        that a CHANGED instant also normalises to the signed one."""
        from datetime import datetime, timezone
        from src.schema.grant_event import GrantEvent
        from src.schema.scope import Scope

        at = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        event = sign_pydantic(GrantEvent(
            event_id="e-t", grant_id="g-t", work_id="w-t", counterparty_id="buyer-t",
            kind="granted", issued_at=at, signature="x",
            scope=Scope(use_type="training", model_class="all_models",
                        attribution_required=False, commercial=True, valid_from=at),
        ), kind="grant", reference="g-t")
        pem = signing.get_active_signer().public_key_pem
        doc = event.model_dump(mode="json")

        for label, shifted in (
            ("one hour later", "2026-08-25T13:00:00+00:00"),
            ("one second later", "2026-08-25T12:00:01Z"),
            ("same wall clock, different offset", "2026-08-25T12:00:00+01:00"),
        ):
            with self.subTest(label):
                self.assertFalse(
                    verify_document(dict(doc, issued_at=shifted), pem),
                    f"a document whose instant moved ({label}) still verified")

    def test_signed_receipt_verifies_and_tampering_is_detected(self):
        receipt = sign_pydantic(_receipt(), kind="receipt", reference="g-1")
        self.assertTrue(is_signature_envelope(receipt.signature))
        pem = signing.get_active_signer().public_key_pem

        doc = receipt.model_dump(mode="json")
        self.assertTrue(verify_document(doc, pem))

        tampered = dict(doc, counterparty_id="someone-else")
        self.assertFalse(verify_document(tampered, pem),
                         "a tampered receipt verified — the signature is decoration")

    def test_temporary_empty_signature_never_survives(self):
        receipt = sign_pydantic(_receipt(signature=""), kind="receipt", reference="g-1")
        self.assertNotEqual(receipt.signature, "")

    def test_cascade_receipts_are_verifiable_in_ephemeral_mode(self):
        """End to end through the real cascade: with a signer configured the
        delivered receipts and the appended revoked event carry envelopes
        that verify — and stop verifying when tampered."""
        from src.gateway.gateway import AgentGateway
        from src.agents.revocation_propagator import RevocationPropagatorAgent
        from src.schema.grant_event import GrantEvent
        from src.schema.scope import Scope
        force_offline(self)

        t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
        gateway = AgentGateway(offline_reads={"grants": [GrantEvent(
            event_id="e1", grant_id="g1", work_id="w1", counterparty_id="cp1",
            scope=Scope(use_type="training", valid_from=t0),
            kind="granted", issued_at=t0, signature="s").model_dump(mode="json")]})
        result = RevocationPropagatorAgent(gateway=gateway).execute_revocation_cascade(
            "w1", "training", operation_id="op-signed")
        pem = signing.get_active_signer().public_key_pem

        self.assertEqual(len(result.issued_notices), 1)
        receipt_doc = result.issued_notices[0].model_dump(mode="json")
        self.assertTrue(verify_document(receipt_doc, pem))

        revoked_doc = next(iter(
            d for d in gateway._offline_writes["grants"].values() if d["kind"] == "revoked"))
        # The stored event was dumped in python mode (datetimes); verify over
        # its JSON-mode form exactly as a reader would receive it.
        from src.schema.grant_event import GrantEvent as GE
        self.assertTrue(verify_document(GE(**revoked_doc).model_dump(mode="json"), pem))


class TestPlaceholderModeIsUnchanged(unittest.TestCase):
    def test_without_a_signer_everything_stays_a_labelled_placeholder(self):
        os.environ.pop("HODI_SIGNING", None)
        signing._active_signer = None
        value = signature_for("receipt", "g-9", b"payload")
        self.assertTrue(is_unsigned_placeholder(value))
        self.assertFalse(is_signature_envelope(value))

    def test_verify_document_refuses_placeholders(self):
        signer = EphemeralEd25519Signer()
        doc = _receipt(signature="UNSIGNED_PLACEHOLDER:receipt:g-1").model_dump(mode="json")
        self.assertFalse(verify_document(doc, signer.public_key_pem))


class TestKmsSignerContract(unittest.TestCase):
    def test_kms_signer_refuses_to_construct_without_configuration(self):
        os.environ.pop("HODI_KMS_KEY_VERSION", None)
        with self.assertRaises(RuntimeError):
            KmsSigner()


if __name__ == "__main__":
    unittest.main()
