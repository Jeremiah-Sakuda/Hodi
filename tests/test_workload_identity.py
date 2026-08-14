"""
Real workload identity (HOD-711).

Two layers, tested at two altitudes:
  * OFFLINE — the conflict-domain → named-database map is coherent: every
    domain has a database, no two conflict domains share a non-default one,
    and the split scripts are generated from the policy module (so they
    cannot drift from the boundary the gateway enforces).
  * E2E (HODI_E2E) — the property that matters: a workload holding one
    domain's SA is refused, BY GOOGLE IAM, reading another domain's
    database. That is the boundary becoming a credential boundary rather
    than an application promise; it can only be proven against the deployed
    infrastructure.
"""

import os
import unittest
from pathlib import Path

from src.schema.iam_policy import (
    AGENT_SA_MAP, CONFLICT_DOMAIN_DATABASE, database_for_role)

ROOT = Path(__file__).resolve().parent.parent


class TestDomainDatabaseMapIsCoherent(unittest.TestCase):
    def test_every_conflict_domain_maps_to_a_database(self):
        domains = {info["conflict_domain"] for info in AGENT_SA_MAP.values()}
        for domain in domains:
            self.assertIn(domain, CONFLICT_DOMAIN_DATABASE,
                          f"conflict domain {domain!r} has no database mapping")

    def test_no_two_conflict_domains_share_a_named_database(self):
        """A shared non-default database would recreate the very co-location
        the split exists to remove."""
        named = [db for db in CONFLICT_DOMAIN_DATABASE.values() if db != "(default)"]
        self.assertEqual(len(named), len(set(named)),
                         "two conflict domains map to the same named database")

    def test_each_role_resolves_to_its_domains_database(self):
        for role, info in AGENT_SA_MAP.items():
            expected = CONFLICT_DOMAIN_DATABASE[info["conflict_domain"]]
            self.assertEqual(database_for_role(role), expected)

    def test_identity_and_evidence_are_on_different_databases(self):
        """The two domains whose co-location would be most damaging."""
        self.assertNotEqual(database_for_role("rights_custodian"),
                            database_for_role("evidence_agent"))

    def test_setup_script_is_generated_from_the_policy_module(self):
        script = (ROOT / "scripts" / "setup_workload_identity.sh").read_text()
        self.assertIn("from src.schema.iam_policy import", script)
        self.assertIn("CONFLICT_DOMAIN_DATABASE", script)

    def test_worker_split_script_binds_the_propagator_sa(self):
        script = (ROOT / "scripts" / "deploy_revocation_worker.sh").read_text()
        self.assertIn("revocation-propagator-sa@", script)
        # It PROVES the deployed identity rather than only reporting it.
        self.assertIn("PROOF", script)
        self.assertIn("FAIL", script)


@unittest.skipUnless(os.environ.get("HODI_E2E") == "1",
                     "Live IAM assertion (HOD-711): set HODI_E2E=1 with gcloud credentials. "
                     "Requires scripts/setup_workload_identity.sh to have run — it asserts a "
                     "cross-domain read is refused by Google IAM, which cannot be shown offline.")
class TestForeignDomainReadIsDeniedByIAM(unittest.TestCase):
    def test_evidence_sa_cannot_read_the_identity_database(self):
        from google.cloud import firestore
        from google.api_core import exceptions as gexc
        from google.auth import impersonated_credentials
        import google.auth

        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        source, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        # Impersonate the EVIDENCE SA and try to read the IDENTITY database.
        evidence_sa = AGENT_SA_MAP["evidence_agent"]["sa_email"]
        identity_db = database_for_role("rights_custodian")
        creds = impersonated_credentials.Credentials(
            source_credentials=source, target_principal=evidence_sa,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"])
        client = firestore.Client(project=project, credentials=creds, database=identity_db)
        with self.assertRaises((gexc.PermissionDenied, gexc.Forbidden),
                               msg="the evidence SA read the identity database — the "
                                   "boundary is not a credential boundary"):
            list(client.collection("artists").limit(1).stream())


if __name__ == "__main__":
    unittest.main()
