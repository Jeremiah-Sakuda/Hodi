"""
Autonomous consent incident response, end to end (HOD-704, HOD-705, HOD-706).

The property under test: an incident's record can be independently
reconstructed — the walls hold during the investigation, the arbiter
concludes only what typed assertions support, containment acts only on
what Hodi administers, and the exported package verifies from its own
bytes (and stops verifying when one of them changes).

Runs entirely offline: fixture scraper (fictional, unnamed), the
gateway's offline stores, and the EPHEMERAL signer — whose envelope says
so.
"""

import copy
import json
import os
import unittest
from pathlib import Path

from src.gateway.gateway import AgentGateway
from src.incident.engine import IncidentEngine
from src.incident.package import export_package, verify_package
from src.schema import signing
from tests.offline_env import force_offline

FIXTURE = json.loads((Path(__file__).resolve().parent.parent
                      / "fixtures" / "incident_scenario.json").read_text())


def _gateway(with_grant: bool) -> AgentGateway:
    grants = [FIXTURE["scenario_b_grant"]] if with_grant else []
    return AgentGateway(offline_reads={
        "crawler_access": [FIXTURE["access_record"]],
        "works": [FIXTURE["work"]],
        "grants": grants,
    })


class IncidentScenarioBase(unittest.TestCase):
    def setUp(self):
        # force_offline RESTORES rather than pops — see tests/offline_env.py.
        # HODI_SIGNING is ours to remove: nothing outside these tests sets it.
        force_offline(self)
        os.environ["HODI_SIGNING"] = "ephemeral"
        signing._active_signer = None
        self.addCleanup(lambda: (os.environ.pop("HODI_SIGNING", None),
                                 setattr(signing, "_active_signer", None)))

    def _run(self, with_grant: bool):
        gateway = _gateway(with_grant)
        engine = IncidentEngine(gateway=gateway)
        result = engine.run(
            work_id=FIXTURE["work"]["work_id"],
            declared_principal=FIXTURE["declared_principal"],
            access_record=FIXTURE["access_record"])
        return gateway, result


class TestScenarioA_NoGrant(IncidentScenarioBase):
    """The fixture scraper fetched the work; no grant ever existed."""

    def test_outside_policy_established_training_not(self):
        _, result = self._run(with_grant=False)
        decision = result.manifest.decision
        statuses = {f.claim: f.status for f in decision.findings}
        self.assertEqual(statuses["ACCESS_OUTSIDE_DECLARED_POLICY"], "ESTABLISHED")
        self.assertEqual(statuses["ACCESS_WITHIN_DECLARED_POLICY"], "NOT_ESTABLISHED")
        self.assertTrue(decision.not_determinable["MODEL_TRAINING_OCCURRED"]
                        .startswith("NOT_ESTABLISHED"))

    def test_lifecycle_is_appended_in_order_and_immutable(self):
        gateway, result = self._run(with_grant=False)
        statuses = [e.status for e in result.lifecycle]
        self.assertEqual(statuses, ["observed", "investigating", "adjudicated",
                                    "contained", "closed"])
        # Every transition is a create-only document in the incidents record.
        written = gateway._offline_writes["incidents"]
        for event in result.lifecycle:
            self.assertIn(event.event_id, written)

    def test_containment_freezes_the_principal_but_revokes_nothing(self):
        gateway, result = self._run(with_grant=False)
        self.assertIsNotNone(result.freeze)
        self.assertIsNone(result.revocation_operation_id,
                          "no grant existed — there was nothing to revoke, and "
                          "revoking anyway would be enforcement, not administration")
        self.assertIn(result.freeze.freeze_id, gateway._offline_writes["negotiation_freezes"])

    def test_the_walls_held_during_the_investigation(self):
        """No denial events: every agent answered inside its own domain, so
        the investigation never even ATTEMPTED a cross-wall read."""
        gateway, _ = self._run(with_grant=False)
        self.assertEqual(gateway.denial_events, [])

    def test_advocates_exculpatory_assertion_is_present_and_reflected(self):
        _, result = self._run(with_grant=False)
        classes = {a.assertion_class for a in result.assertions}
        self.assertIn("ACCESS_DOES_NOT_ESTABLISH_TRAINING", classes)
        self.assertIn("counterparty advocate",
                      result.manifest.decision.not_determinable["MODEL_TRAINING_OCCURRED"])

    def test_package_verifies_and_one_tampered_byte_fails(self):
        _, result = self._run(with_grant=False)
        package = export_package(result)

        report = verify_package(package)
        self.assertTrue(report.all_ok,
                        "untampered package failed: " +
                        "; ".join(label for ok, label in report.checks if not ok))
        self.assertEqual(report.conclusions["ACCESS_OUTSIDE_DECLARED_POLICY"], "ESTABLISHED")
        self.assertEqual(report.conclusions["MODEL_TRAINING_OCCURRED"], "NOT_ESTABLISHED")

        tampered = copy.deepcopy(package)
        tampered["observations"][0]["path"] = "/somewhere-else"
        self.assertFalse(verify_package(tampered).all_ok,
                         "a tampered observation still verified")

        tampered2 = copy.deepcopy(package)
        tampered2["manifest"]["subject_principal"] = "an-innocent-party"
        self.assertFalse(verify_package(tampered2).all_ok,
                         "a tampered manifest still verified")

    def test_decision_reproduction_catches_a_swapped_decision(self):
        """The self-proving check: replacing the recorded decision with a
        differently-concluded one fails reproduction even if everything else
        is left intact."""
        _, result = self._run(with_grant=False)
        package = export_package(result)
        tampered = copy.deepcopy(package)
        for finding in tampered["manifest"]["decision"]["findings"]:
            if finding["claim"] == "ACCESS_OUTSIDE_DECLARED_POLICY":
                finding["status"] = "NOT_ESTABLISHED"
                finding["basis"] = []
        report = verify_package(tampered)
        self.assertFalse(report.all_ok)

    def test_manifest_prose_passes_the_overclaim_lint(self):
        """The honesty invariants extend to the new surface: no manifest text
        may carry a training-membership phrase the lint enumerates. lint_text
        RAISES on a violation — a raise here is the test failing."""
        from src.evidence.overclaim_lint import OverclaimLint
        _, result = self._run(with_grant=False)
        lint = OverclaimLint()
        for text in result.manifest.limitations + [result.manifest.grant_state_basis]:
            lint.lint_text(text)

    def test_frozen_principal_is_refused_at_the_license_route(self):
        """Containment reaches the production surface: after the incident,
        the frozen principal's signed, well-formed license request is 403."""
        import base64
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api import buyer_api
        from src.api.auth import (InMemoryCredentialStore, compute_signature,
                                  HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_SIGNATURE)
        from datetime import datetime, timezone

        gateway, result = self._run(with_grant=False)
        principal = FIXTURE["declared_principal"]

        buyer_api.set_gateway(gateway)
        self.addCleanup(lambda: buyer_api.set_gateway(None))
        original = buyer_api._credential_store
        buyer_api.set_credential_store(InMemoryCredentialStore({
            "key-frozen": {"counterparty_id": principal, "secret": "s3", "active": True}}))
        self.addCleanup(lambda: buyer_api.set_credential_store(original))

        app = FastAPI()
        app.include_router(buyer_api.router)
        client = TestClient(app)
        body = json.dumps({
            "work_id": FIXTURE["work"]["work_id"],
            "requested_scope": {"use_type": "human_reference",
                                "valid_from": "2026-08-14T00:00:00Z"},
            "raw_document_b64": base64.b64encode(b"doc").decode()}).encode()
        ts = datetime.now(timezone.utc).isoformat()
        r = client.post("/api/v1/license", content=body, headers={
            "Content-Type": "application/json",
            HEADER_KEY_ID: "key-frozen", HEADER_TIMESTAMP: ts,
            HEADER_SIGNATURE: compute_signature("s3", "key-frozen", ts, body)})
        self.assertEqual(r.status_code, 403)
        self.assertIn(result.manifest.incident_id, r.json()["detail"])


class TestScenarioB_GrantExistedButScopeInconsistent(IncidentScenarioBase):
    """The scraper HELD a rag_retrieval grant — but the work's declared
    policy forbids automated ingestion. Outside policy on the custodian's
    narrower basis; containment terminates the grant through the real
    cascade, idempotently."""

    def test_outside_policy_on_scope_basis_and_grant_terminated(self):
        gateway, result = self._run(with_grant=True)
        statuses = {f.claim: f.status for f in result.manifest.decision.findings}
        self.assertEqual(statuses["ACCESS_OUTSIDE_DECLARED_POLICY"], "ESTABLISHED")
        self.assertIsNotNone(result.revocation_operation_id)
        revoked = [d for d in gateway._offline_writes.get("grants", {}).values()
                   if d.get("kind") == "revoked"]
        self.assertEqual(len(revoked), 1)
        self.assertEqual(len(gateway._offline_writes.get("revocation_notices", {})), 1)

    def test_rerunning_the_incidents_containment_does_not_double_anything(self):
        gateway, result = self._run(with_grant=True)
        from src.agents.revocation_propagator import RevocationPropagatorAgent
        RevocationPropagatorAgent(gateway=gateway).execute_revocation_cascade(
            work_id=FIXTURE["work"]["work_id"],
            revoked_use_type="rag_retrieval",
            operation_id=result.revocation_operation_id)
        revoked = [d for d in gateway._offline_writes["grants"].values()
                   if d.get("kind") == "revoked"]
        self.assertEqual(len(revoked), 1)
        self.assertEqual(len(gateway._offline_writes["revocation_notices"]), 1)


class TestDeterminism(IncidentScenarioBase):
    def test_same_assertions_reproduce_the_same_decision(self):
        from src.agents.consent_arbiter import adjudicate_assertions
        _, result = self._run(with_grant=False)
        d1 = result.manifest.decision
        d2 = adjudicate_assertions(result.assertions, result.manifest.incident_id,
                                   decision_id=d1.decision_id, decided_at=d1.decided_at)
        self.assertEqual(d1.model_dump(mode="json"), d2.model_dump(mode="json"))


if __name__ == "__main__":
    unittest.main()
