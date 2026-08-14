"""
Assertion authority (HOD-703): who may CLAIM what, enforced structurally.

Two layers, tested separately because they fail differently:
  * the SCHEMA — a training-membership claim has no assertion class, so it
    cannot be constructed as data at all;
  * the AUTHORITY MATRIX — a role submitting a class outside its epistemic
    position is refused at the gateway with a structured denial.
"""

import os
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.schema.assertion import TypedAssertion, IncidentDecision, ClaimFinding
from src.schema.assertion_authority import ASSERTION_AUTHORITY, may_assert

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _assertion(cls, role) -> TypedAssertion:
    return TypedAssertion(
        assertion_id="a-1", assertion_class=cls, asserted_by_role=role,
        subject_work_id="work-essay-001", subject_principal="fictional-scraper-co",
        basis="test", recorded_at=NOW)


class TestTheUnsayableStaysUnsayable(unittest.TestCase):
    """The structural layer: the claim dies at the schema, before any
    authority check could even run."""

    def test_training_membership_is_not_a_constructible_assertion(self):
        for forbidden in ("MODEL_TRAINED_ON_WORK", "TRAINING_MEMBERSHIP",
                          "WORK_WAS_IN_TRAINING_SET"):
            with self.subTest(cls=forbidden):
                with self.assertRaises(ValidationError):
                    _assertion(forbidden, "evidence_agent")

    def test_no_authority_entry_grants_a_nonexistent_class(self):
        """Even the matrix cannot smuggle it in: no role's authority set
        contains a training class."""
        for role, classes in ASSERTION_AUTHORITY.items():
            for cls in classes:
                self.assertNotIn("TRAIN", cls.upper().replace("DOES_NOT_ESTABLISH_TRAINING", ""),
                                 f"{role} holds a training-adjacent authority: {cls}")

    def test_established_training_is_not_a_constructible_finding(self):
        with self.assertRaises(ValidationError):
            ClaimFinding(claim="MODEL_TRAINING_OCCURRED", status="ESTABLISHED")

    def test_decision_cannot_answer_a_not_determinable_question(self):
        with self.assertRaises(ValidationError):
            IncidentDecision(
                decision_id="d", incident_id="i", policy_version="consent_policy_v1",
                findings=[],
                not_determinable={"MODEL_TRAINING_OCCURRED": "ESTABLISHED — smuggled"},
                decided_at=NOW)

    def test_decision_cannot_drop_the_training_boundary(self):
        with self.assertRaises(ValidationError):
            IncidentDecision(
                decision_id="d", incident_id="i", policy_version="consent_policy_v1",
                findings=[], not_determinable={}, decided_at=NOW)


class TestAuthorityMatrix(unittest.TestCase):
    def test_each_role_may_assert_its_own_classes(self):
        for role, classes in ASSERTION_AUTHORITY.items():
            for cls in classes:
                self.assertTrue(may_assert(role, cls))

    def test_roles_may_not_assert_each_others_classes(self):
        self.assertFalse(may_assert("evidence_agent", "GRANT_EXISTED"))
        self.assertFalse(may_assert("licensing_negotiator", "OBSERVED_HTTP_ACCESS"))
        self.assertFalse(may_assert("rights_custodian", "GRANT_DID_NOT_EXIST"))
        self.assertFalse(may_assert("counterparty_advocate", "REVOCATION_INITIATED"))

    def test_the_arbiter_asserts_nothing(self):
        """An adjudicator that could also be a witness would be interested."""
        self.assertEqual(ASSERTION_AUTHORITY["consent_arbiter"], frozenset())

    def test_unknown_roles_fail_closed(self):
        self.assertFalse(may_assert("some_new_role", "OBSERVED_HTTP_ACCESS"))


class TestGatewayEnforcement(unittest.TestCase):
    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        self.gateway = AgentGateway()

    def test_authorized_assertion_passes(self):
        a = self.gateway.submit_assertion(
            calling_sa="evidence-agent-sa@hodi-2026.iam.gserviceaccount.com",
            calling_role_key="evidence_agent",
            assertion=_assertion("OBSERVED_HTTP_ACCESS", "evidence_agent"))
        self.assertEqual(a.assertion_class, "OBSERVED_HTTP_ACCESS")

    def test_out_of_authority_assertion_is_a_structured_denial(self):
        """The review's demo moment: the evidence agent reaching beyond its
        epistemic position — here, trying to answer the negotiator's
        question — is refused with the policy named."""
        with self.assertRaises(GatewayPolicyDenial) as ctx:
            self.gateway.submit_assertion(
                calling_sa="evidence-agent-sa@hodi-2026.iam.gserviceaccount.com",
                calling_role_key="evidence_agent",
                assertion=_assertion("GRANT_EXISTED", "evidence_agent"))
        denial = ctx.exception.denial
        self.assertEqual(denial.policy_consulted, "assertion_authority_v1")
        self.assertEqual(denial.outcome, "DENIED")
        self.assertIn("lacks authority", denial.reason)
        self.assertEqual(len(self.gateway.denial_events), 1)


class TestConflictTopologyWithFiveAgents(unittest.TestCase):
    """The founding rule survives the fifth agent: no role holds two of the
    four conflict domains, and the arbiter holds NONE of them."""

    DOMAIN_MARKERS = {
        "identity": {"artists", "works", "control_proofs"},
        "buyer_terms": {"buyer_terms"},
        "evidence": {"crawler_access", "canaries", "evidence_records"},
        "revocation": {"revocation_notices", "revocation_outbox"},
    }

    def _domains_held(self, role) -> set:
        from src.schema.iam_policy import AGENT_SA_MAP
        held = set()
        permitted = {c if isinstance(c, str) else c["collection"]
                     for c in AGENT_SA_MAP[role]["permitted_collections"]}
        for domain, markers in self.DOMAIN_MARKERS.items():
            if permitted & markers:
                held.add(domain)
        return held

    def test_no_role_holds_two_domains(self):
        from src.schema.iam_policy import AGENT_SA_MAP
        for role in AGENT_SA_MAP:
            self.assertLessEqual(
                len(self._domains_held(role)), 1,
                f"{role} holds multiple conflict domains: {self._domains_held(role)}")

    def test_the_arbiter_holds_no_domain_at_all(self):
        self.assertEqual(self._domains_held("consent_arbiter"), set())


class TestArbiterWallsAtTheGateway(unittest.TestCase):
    """The arbiter's paired negatives (HOD-704): assertions in, nothing else."""

    def setUp(self):
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))
        from src.agents.consent_arbiter import ConsentArbiterAgent
        self.arbiter = ConsentArbiterAgent(AgentGateway())

    def test_arbiter_cannot_read_raw_evidence(self):
        with self.assertRaises(GatewayPolicyDenial):
            self.arbiter.read_raw_evidence()

    def test_arbiter_cannot_read_buyer_terms(self):
        with self.assertRaises(GatewayPolicyDenial):
            self.arbiter.read_buyer_terms("fictional-scraper-co")

    def test_arbiter_cannot_read_artist_identity(self):
        with self.assertRaises(GatewayPolicyDenial):
            self.arbiter.read_artist_identity()

    def test_arbiter_cannot_rewrite_grant_history(self):
        """HOD-704's sharpest AC: the adjudicator has no write path to the
        history it rules on."""
        with self.assertRaises(GatewayPolicyDenial):
            self.arbiter.rewrite_grant_history("evt-x", {"kind": "granted"})

    def test_arbiter_can_write_its_own_incident_record(self):
        self.arbiter.record_incident("incident-t:00:observed", {"status": "observed"})


if __name__ == "__main__":
    unittest.main()
