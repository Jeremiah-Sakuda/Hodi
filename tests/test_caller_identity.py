"""
Caller identity (HOD-717).

Two properties, and the difference between them is the whole point:

  1. THE BINDING IS CHECKED. A caller's service account must be the one
     iam_policy.py declares for its role — enforced on every gateway call,
     not merely logged. Before this, `calling_role_key` chose the policy and
     `calling_sa` was written to the denial event and otherwise ignored.

  2. THE ORIGIN IS STATED, AND CAN BE REQUIRED. An identity is either
     `oidc_verified` (a Google-signed token whose issuer, audience, expiry
     and verified email were checked — non-forgeable) or
     `in_process_trusted` (code in this process — exactly as trustworthy as
     the process, and no more). Strict mode refuses the second category,
     which is the posture a split-service deployment runs in.

Checking the binding does NOT make an in-process string non-forgeable. It
makes the forgery a named category that a deployment can refuse. These tests
assert both halves, including the honest limit.

NOT covered here: the cryptographic verification of Google's signature,
which is delegated to google.oauth2.id_token and needs Google's keys. Every
rule around it — issuer, audience, expiry, email verification, the
email→role mapping — is covered, with an injected verifier standing in for
the signature check.
"""

import os
import time
import unittest

from src.gateway.caller_identity import (
    CallerIdentity, IdentityVerificationError, STRICT_ENV,
    role_for_service_account, strict_identity_required)
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.schema.iam_policy import AGENT_SA_MAP
from tests.offline_env import force_offline

NEGOTIATOR_SA = AGENT_SA_MAP["licensing_negotiator"]["sa_email"]
CUSTODIAN_SA = AGENT_SA_MAP["rights_custodian"]["sa_email"]
EVIDENCE_SA = AGENT_SA_MAP["evidence_agent"]["sa_email"]

AUDIENCE = "https://hodi-evidence-endpoint.example"


def _claims(**overrides):
    base = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": CUSTODIAN_SA,
        "email_verified": True,
        "sub": "123456789",
        "exp": time.time() + 600,
    }
    base.update(overrides)
    return base


def _verifier(claims):
    """Stands in for Google's signature check, so the claim rules are testable."""
    return lambda token, audience: claims


class TestTheBindingIsChecked(unittest.TestCase):
    def test_in_process_derives_the_sa_from_the_policy(self):
        identity = CallerIdentity.in_process("rights_custodian")
        self.assertEqual(identity.service_account, CUSTODIAN_SA)
        self.assertEqual(identity.verification, "in_process_trusted")

    def test_an_unknown_role_cannot_be_asserted(self):
        with self.assertRaises(IdentityVerificationError):
            CallerIdentity.in_process("shadow_role")

    def test_a_mismatched_sa_and_role_is_refused(self):
        """The check that did not exist: presenting one role with another
        role's service account."""
        with self.assertRaises(IdentityVerificationError) as ctx:
            CallerIdentity.coerce(None, calling_sa=CUSTODIAN_SA,
                                  calling_role_key="licensing_negotiator")
        self.assertIn("does not match the identity", str(ctx.exception))

    def test_a_matching_pair_is_accepted(self):
        identity = CallerIdentity.coerce(None, calling_sa=NEGOTIATOR_SA,
                                         calling_role_key="licensing_negotiator")
        self.assertEqual(identity.role_key, "licensing_negotiator")

    def test_role_lookup_reverses_the_policy(self):
        self.assertEqual(role_for_service_account(EVIDENCE_SA), "evidence_agent")
        self.assertIsNone(role_for_service_account("attacker@evil.example"))
        self.assertIsNone(role_for_service_account(None))


class TestGatewayEnforcesTheBinding(unittest.TestCase):
    def setUp(self):
        force_offline(self)
        self.gateway = AgentGateway()

    def test_a_spoofed_role_is_a_structured_denial(self):
        """The evidence agent's identity claiming the custodian's role, which
        would otherwise have read artist identity: refused, and the refusal is
        an auditable event naming the identity policy."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.gateway.read_collection(
                calling_sa=EVIDENCE_SA, calling_role_key="rights_custodian",
                target_collection="artists")
        denial = ctx.exception.denial
        self.assertEqual(denial.policy_consulted, "caller_identity_v1")
        self.assertEqual(denial.outcome, "DENIED")
        self.assertEqual(len(self.gateway.denial_events), 1)

    def test_the_denial_names_the_collection_that_was_attempted(self):
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.gateway.read_collection(
                calling_sa=EVIDENCE_SA, calling_role_key="rights_custodian",
                target_collection="artists")
        self.assertEqual(ctx.exception.denial.requested_collection, "artists")

    def test_a_correctly_bound_caller_still_passes(self):
        """The paired positive: binding enforcement must not deny everything."""
        rows = self.gateway.read_collection(
            calling_sa=CUSTODIAN_SA, calling_role_key="rights_custodian",
            target_collection="works")
        self.assertEqual(rows, [])

    def test_writes_are_bound_too(self):
        with self.assertRaises(GatewayPolicyDenial):
            self.gateway.write_document(
                calling_sa=EVIDENCE_SA, calling_role_key="revocation_propagator",
                target_collection="grants", doc_id="d", data={})


class TestOidcDerivedIdentity(unittest.TestCase):
    def test_a_valid_token_yields_the_role_of_its_verified_email(self):
        identity = CallerIdentity.from_oidc(
            "token", AUDIENCE, verifier=_verifier(_claims()))
        self.assertEqual(identity.role_key, "rights_custodian")
        self.assertEqual(identity.verification, "oidc_verified")
        self.assertTrue(identity.is_verified)
        self.assertEqual(identity.token_subject, "123456789")

    def test_the_caller_does_not_get_to_choose_its_role(self):
        """The non-forgeable property: role comes from the VERIFIED email, so
        a caller holding the evidence SA's token is the evidence agent no
        matter what it would prefer to be."""
        identity = CallerIdentity.from_oidc(
            "token", AUDIENCE, verifier=_verifier(_claims(email=EVIDENCE_SA)))
        self.assertEqual(identity.role_key, "evidence_agent")

    def test_a_foreign_issuer_is_refused(self):
        with self.assertRaises(IdentityVerificationError) as ctx:
            CallerIdentity.from_oidc(
                "token", AUDIENCE, verifier=_verifier(_claims(iss="https://evil.example")))
        self.assertIn("issuer", str(ctx.exception))

    def test_a_token_minted_for_another_service_is_refused(self):
        """Audience checking is what stops a token replayed from elsewhere."""
        with self.assertRaises(IdentityVerificationError) as ctx:
            CallerIdentity.from_oidc(
                "token", AUDIENCE, verifier=_verifier(_claims(aud="https://other.example")))
        self.assertIn("audience", str(ctx.exception))

    def test_an_expired_token_is_refused(self):
        with self.assertRaises(IdentityVerificationError):
            CallerIdentity.from_oidc(
                "token", AUDIENCE, verifier=_verifier(_claims(exp=time.time() - 1)))

    def test_a_token_with_no_expiry_is_refused(self):
        claims = _claims()
        del claims["exp"]
        with self.assertRaises(IdentityVerificationError):
            CallerIdentity.from_oidc("token", AUDIENCE, verifier=_verifier(claims))

    def test_an_unverified_email_is_refused(self):
        with self.assertRaises(IdentityVerificationError):
            CallerIdentity.from_oidc(
                "token", AUDIENCE, verifier=_verifier(_claims(email_verified=False)))

    def test_an_unknown_service_account_gets_no_role(self):
        with self.assertRaises(IdentityVerificationError) as ctx:
            CallerIdentity.from_oidc(
                "token", AUDIENCE, verifier=_verifier(_claims(email="stranger@evil.example")))
        self.assertIn("maps to no role", str(ctx.exception))

    def test_a_failing_signature_check_is_a_refusal_not_a_crash(self):
        def explode(token, audience):
            raise ValueError("bad signature")
        with self.assertRaises(IdentityVerificationError):
            CallerIdentity.from_oidc("token", AUDIENCE, verifier=explode)


class TestStrictMode(unittest.TestCase):
    """The executable half of 'when we split the services, this becomes real'."""

    def setUp(self):
        force_offline(self)
        self._saved = os.environ.get(STRICT_ENV)
        os.environ[STRICT_ENV] = "1"
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop(STRICT_ENV, None)
        if self._saved is not None:
            os.environ[STRICT_ENV] = self._saved

    def test_strict_mode_is_off_by_default(self):
        os.environ.pop(STRICT_ENV, None)
        self.assertFalse(strict_identity_required())

    def test_an_in_process_caller_is_refused_under_strict_mode(self):
        gateway = AgentGateway()
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            gateway.read_collection(calling_sa=CUSTODIAN_SA,
                                    calling_role_key="rights_custodian",
                                    target_collection="works")
        self.assertEqual(ctx.exception.denial.policy_consulted, "caller_identity_v1")
        self.assertIn("verified workload identity", ctx.exception.denial.reason)

    def test_an_oidc_verified_caller_is_served_under_strict_mode(self):
        gateway = AgentGateway()
        identity = CallerIdentity.from_oidc(
            "token", AUDIENCE, verifier=_verifier(_claims()))
        rows = gateway.read_collection(
            calling_sa=None, calling_role_key=None,
            target_collection="works", identity=identity)
        self.assertEqual(rows, [])


class TestServiceAccountsAreNeverRetyped(unittest.TestCase):
    """
    Enforcing the binding immediately surfaced a real defect: two production
    paths used SA strings the policy does not declare
    ('licensing-negotiator@…' and 'revocation-propagator@…', both missing the
    '-sa'), so every denial event from the licensing path and every revocation
    write recorded an identity that does not exist. This guard stops a
    hand-typed service account from re-entering.
    """

    def test_no_source_file_hardcodes_an_agent_service_account(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        declared = {i["sa_email"] for i in AGENT_SA_MAP.values()}
        pattern = re.compile(r'"([a-z0-9-]*(?:custodian|negotiator|evidence-agent|propagator|arbiter)'
                             r'[a-z0-9-]*@hodi-2026\.iam\.gserviceaccount\.com)"')
        offenders = []
        for base in ("src", "scripts"):
            for path in sorted((root / base).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                if path.name == "iam_policy.py":
                    continue  # the source of truth is where the literals belong
                for line_no, line in enumerate(path.read_text().splitlines(), 1):
                    for match in pattern.finditer(line):
                        offenders.append(
                            f"{path.relative_to(root)}:{line_no}: {match.group(1)}"
                            + ("  (NOT EVEN DECLARED)" if match.group(1) not in declared else ""))
        self.assertEqual(
            offenders, [],
            "agent service accounts must be read from AGENT_SA_MAP, never retyped — "
            "a literal that drifts from the policy poisons every audit record it "
            "appears in:\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
