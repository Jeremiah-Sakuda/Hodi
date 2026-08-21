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
        self.assertIn("revocation-default-only", script)
        self.assertIn("HODI_SERVICE_ROLE=revocation_propagator", script)
        self.assertIn("roles/run.invoker", script)

    def test_worker_has_no_unconditioned_database_grant(self):
        """The split is false if a broad viewer or append role sits beside the
        default-database condition."""
        script = (ROOT / "scripts" / "deploy_revocation_worker.sh").read_text()
        self.assertIn("resource.name.endsWith('/databases/(default)')", script)
        self.assertIn("remove-iam-policy-binding", script)
        self.assertIn("propagator still holds unconditioned database grants", script)

    def test_main_deploy_requires_the_private_worker(self):
        script = (ROOT / "scripts" / "deploy.sh").read_text()
        self.assertIn("./scripts/deploy_revocation_worker.sh", script)
        self.assertIn("no live in-process fallback", script)

    def test_general_deploy_cannot_restore_broad_database_roles(self):
        """A routine redeploy must preserve IAM narrowing already in place."""
        script = (ROOT / "scripts" / "deploy_gcp.sh").read_text()
        self.assertIn("front-door-default-only", script)
        self.assertIn("revocation-default-only", script)
        self.assertIn("refusing to guess and broaden access", script)
        self.assertNotIn("2>/dev/null || true", script)

    def test_domain_deploy_does_not_mask_unconditional_role_removal(self):
        script = (ROOT / "scripts" / "deploy_domain_services.sh").read_text()
        self.assertNotIn("--condition=None --quiet >/dev/null 2>&1 || true", script)


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
        # ADC first; fall back to the gcloud CLI token — this machine has user
        # auth but no ADC file, the same quirk every script in this repo
        # handles (see gateway._build_firestore_client).
        try:
            source, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
        except google.auth.exceptions.DefaultCredentialsError:
            import subprocess
            from google.oauth2 import credentials as oauth2_credentials
            token = subprocess.check_output(
                ["gcloud", "auth", "print-access-token"],
                stderr=subprocess.DEVNULL).decode().strip()
            source = oauth2_credentials.Credentials(token)
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


@unittest.skipUnless(os.environ.get("HODI_E2E") == "1",
                     "Live IAM assertion (HOD-733): set HODI_E2E=1 with gcloud credentials.")
class TestFrontDoorCannotReachDomainDatabases(unittest.TestCase):
    """
    The property the four-service split exists to create.

    Deploying a service per domain changes nothing while the front door still
    holds unconditioned grants — it could read every domain database itself and
    the delegation would be decoration. So the runtime identity is conditioned
    to `(default)`, and these two tests are the pair that matters: it must be
    REFUSED on a domain database, and still WORK on the shared grant log.
    Asserting only the first would pass on a completely broken service account.
    """

    def _impersonate_or_skip(self, sa_email, database):
        """
        Build a client acting as `sa_email`, or SKIP with the reason.

        Impersonation needs serviceAccountTokenCreator on the target, and the
        CI release verifier deliberately does not hold it on the front door —
        the point of that identity is that it holds as little as possible. A
        runner that cannot impersonate must say so and skip, not hang: the
        first CI run of this test spent twenty minutes in credential retry
        backoff before it was cancelled, which is a worse failure than a red
        test because nothing tells you what is wrong.
        """
        try:
            return self._impersonate(sa_email, database)
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"cannot impersonate {sa_email} from this runner: "
                          f"{type(e).__name__}: {e}")

    def test_the_front_door_holds_no_unconditioned_database_grant(self):
        """
        The policy-SHAPE half, which needs only read access to IAM and
        therefore runs anywhere the live suite runs.

        An unconditioned grant beside a conditioned one narrows nothing. This
        catches that directly, and it catches it even in a run where a read
        happened to fail for some unrelated reason — which a denial test alone
        would quietly pass.
        """
        import json as _json
        import subprocess as _sp
        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        front_door = f"hodi-runtime-sa@{project}.iam.gserviceaccount.com"
        out = _sp.run(["gcloud", "projects", "get-iam-policy", project, "--format=json"],
                      capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest(f"could not read the project IAM policy: {out.stderr.strip()[:200]}")
        policy = _json.loads(out.stdout)
        member = f"serviceAccount:{front_door}"
        offenders = [b["role"] for b in policy.get("bindings", [])
                     if member in b.get("members", []) and not b.get("condition")
                     and ("datastore" in b["role"] or "GrantWriter" in b["role"])]
        self.assertFalse(
            offenders,
            f"the front door holds UNCONDITIONED database grants {offenders}. It can read every "
            "domain database directly, so the domain services are decoration.")

    def _impersonate(self, sa_email, database):
        from google.cloud import firestore
        from google.auth import impersonated_credentials
        import google.auth

        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        try:
            source, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
        except google.auth.exceptions.DefaultCredentialsError:
            import subprocess
            from google.oauth2 import credentials as oauth2_credentials
            token = subprocess.check_output(
                ["gcloud", "auth", "print-access-token"],
                stderr=subprocess.DEVNULL).decode().strip()
            source = oauth2_credentials.Credentials(token)
        creds = impersonated_credentials.Credentials(
            source_credentials=source, target_principal=sa_email,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"])
        # MINT THE TOKEN NOW. Impersonated credentials are lazy: building them
        # always succeeds, and the failure to mint surfaces later, inside the
        # gRPC read, as a transport error indistinguishable from the
        # PermissionDenied this test is trying to observe. That is how the first
        # CI run turned "this runner may not impersonate" into six errors and
        # twenty-four minutes of retries. Refreshing here separates "cannot
        # act as this identity" (skip) from "acted as it and was refused"
        # (the assertion).
        from google.auth.transport.requests import Request as _AuthRequest
        creds.refresh(_AuthRequest())
        return firestore.Client(project=project, credentials=creds, database=database)

    def test_front_door_is_denied_every_domain_database(self):
        from google.api_core import exceptions as gexc
        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        front_door = f"hodi-runtime-sa@{project}.iam.gserviceaccount.com"
        for role, collection in (("rights_custodian", "works"),
                                 ("evidence_agent", "crawler_access"),
                                 ("licensing_negotiator", "buyer_terms"),
                                 ("consent_arbiter", "incident_assertions")):
            database = database_for_role(role)
            if database == "(default)":
                continue
            with self.subTest(database=database):
                client = self._impersonate_or_skip(front_door, database)
                with self.assertRaises(
                        (gexc.PermissionDenied, gexc.Forbidden),
                        msg=(f"the front door read {database}. The domain services are "
                             "decoration while it can reach the data itself.")):
                    list(client.collection(collection).limit(1).stream())

    def test_front_door_can_still_read_the_shared_grant_log(self):
        """
        The other half. A narrowing that also broke the grant log would pass the
        test above and leave the system unable to answer a licensing question.
        """
        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        front_door = f"hodi-runtime-sa@{project}.iam.gserviceaccount.com"
        client = self._impersonate_or_skip(front_door, "(default)")
        list(client.collection("grants").limit(1).stream())  # must not raise
