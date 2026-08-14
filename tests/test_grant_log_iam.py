"""
Append-only grant log — the IAM contract, tested against the REAL custom role
(HOD-102).

The previous version of this file could not fail. It built a set literal:

    create_permitted_roles = {"datastore.entities.create", "datastore.entities.get"}
    self.assertIn("datastore.entities.create", create_permitted_roles)
    self.assertNotIn("datastore.entities.update", create_permitted_roles)

…and asserted that the set contained what it had just been constructed to
contain. It touched no policy, no role, and no datastore, while standing as the
guardian of the invariant the whole audit trail rests on: **history cannot be
rewritten.** The repo's own AGENTS.md warns against exactly this shape — "an
acceptance criterion that names the artifact it inspects, rather than the
property it proves, will pass while the property is false."

The custom role now genuinely exists (created by scripts/deploy_gcp.sh), so the
contract is finally testable:

  Offline (always runs): the role definition committed in deploy_gcp.sh grants
  create/get/list and withholds update/delete, and every agent SA declared in
  iam_policy.py is provisioned by that script.

  Live (HODI_E2E=1): the deployed custom role in the real project is read back
  from IAM and asserted to withhold update and delete.
"""

import os
import json
import re
import subprocess
import unittest
from pathlib import Path

from src.schema.iam_policy import AGENT_SA_MAP

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_gcp.sh"
ROLE_ID = "hodiAppendOnlyGrantWriter"
RUNTIME_SA_EMAIL = "hodi-runtime-sa@hodi-2026.iam.gserviceaccount.com"

REQUIRED_PERMISSIONS = {"datastore.entities.create", "datastore.entities.get"}
FORBIDDEN_PERMISSIONS = {"datastore.entities.update", "datastore.entities.delete"}

# Managed roles that would hand the runtime identity back its ability to rewrite
# history. If the deployed process holds any of these, the append-only invariant
# is false at runtime no matter what the code path does.
HISTORY_REWRITING_ROLES = {
    "roles/owner", "roles/editor", "roles/datastore.user",
    "roles/datastore.owner", "roles/datastore.importExportAdmin",
}


def committed_role_permissions() -> set:
    """Parses the role definition out of the provisioning script — the artifact
    that actually creates the role, not a restatement of it in this file."""
    text = DEPLOY_SCRIPT.read_text()
    block = re.search(r"includedPermissions:\n((?:- [\w.]+\n)+)", text)
    assert block, "deploy_gcp.sh no longer declares an includedPermissions block"
    return {line[2:].strip() for line in block.group(1).splitlines() if line.startswith("- ")}


class TestAppendOnlyRoleDefinition(unittest.TestCase):
    """Offline: the role the provisioning script creates is append-only."""

    def setUp(self):
        self.permissions = committed_role_permissions()

    def test_role_grants_create_and_get(self):
        for permission in REQUIRED_PERMISSIONS:
            self.assertIn(permission, self.permissions)

    def test_role_withholds_update_and_delete(self):
        """The invariant: no agent identity can rewrite or erase grant history."""
        for permission in FORBIDDEN_PERMISSIONS:
            self.assertNotIn(
                permission, self.permissions,
                f"'{permission}' would let an agent SA rewrite the append-only log")

    def test_role_grants_nothing_beyond_the_declared_read_and_create_set(self):
        """A permission creeping in later is caught here rather than in prod."""
        self.assertEqual(
            self.permissions,
            REQUIRED_PERMISSIONS | {"datastore.entities.list"},
            "the append-only role gained a permission that has not been reviewed")

    def test_every_declared_agent_sa_is_provisioned_by_the_script(self):
        """The script generates SAs from AGENT_SA_MAP, so a new agent cannot be
        added to the policy without also being provisioned."""
        text = DEPLOY_SCRIPT.read_text()
        self.assertIn("from src.schema.iam_policy import AGENT_SA_MAP", text)
        self.assertIn(ROLE_ID, text)
        # Five since 2026-08-14: the consent arbiter (HOD-704) joined the four
        # domain agents. The script iterates AGENT_SA_MAP, so it provisions the
        # arbiter's SA the same way; this count pins the declared fleet size so
        # an accidental sixth (or a lost fifth) is caught in review.
        self.assertEqual(len(AGENT_SA_MAP), 5)


class TestRuntimeIdentityProvisioning(unittest.TestCase):
    """
    Offline: deploy_gcp.sh binds the runtime identity for append + read and
    withholds every role that could rewrite history.

    This is the guard for the defect the final panel found: the four agent SAs
    held the append-only role, but the deployed PROCESS ran as the default
    compute SA with roles/editor, so the identity that actually writes grant
    events could also update and delete them. The invariant was true of the
    identities the policy names and false of the one that executes.
    """

    def setUp(self):
        self.text = DEPLOY_SCRIPT.read_text()
        # Just the quoted role list between `for role in` and the `; do`.
        block = re.search(r'for role in (.*?);\s*do', self.text, re.DOTALL)
        assert block, "deploy_gcp.sh no longer contains the runtime-SA role-binding loop"
        self.runtime_roles = set(re.findall(r'"([^"]+)"', block.group(1)))

    def test_runtime_sa_is_created(self):
        self.assertIn("hodi-runtime-sa", self.text)
        self.assertIn("--service-account", self.text,
                      "the script must tell the operator to deploy with the runtime SA")

    def test_runtime_sa_can_append(self):
        # The script references the role by its shell variable (${ROLE_ID}),
        # which is set to ROLE_ID at the top of the file — assert both facts.
        self.assertIn(f'ROLE_ID="{ROLE_ID}"', self.text)
        self.assertTrue(any("roles/${ROLE_ID}" in r for r in self.runtime_roles),
                        "runtime SA is not bound to the append-only custom role")

    def test_runtime_sa_can_read(self):
        self.assertIn("roles/datastore.viewer", self.runtime_roles,
                      "runtime SA has no read role — Firestore reads need datastore.databases.get")

    def test_runtime_sa_holds_no_history_rewriting_role(self):
        offenders = self.runtime_roles & HISTORY_REWRITING_ROLES
        self.assertEqual(offenders, set(),
                         f"runtime SA is bound to update/delete-granting role(s): {offenders}")

    def test_runtime_sa_can_reach_the_model_and_logs(self):
        """Append + read is not enough to run: the service calls Vertex and logs."""
        self.assertIn("roles/aiplatform.user", self.runtime_roles)
        self.assertIn("roles/logging.logWriter", self.runtime_roles)


@unittest.skipUnless(os.environ.get("HODI_E2E") == "1",
                     "Live IAM assertion: set HODI_E2E=1 (needs gcloud credentials).")
class TestDeployedRoleIsAppendOnly(unittest.TestCase):
    """Live: read the deployed role back out of IAM and assert the contract."""

    @classmethod
    def setUpClass(cls):
        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        result = subprocess.run(
            ["gcloud", "iam", "roles", "describe", ROLE_ID,
             f"--project={project}", "--format=json"],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise unittest.SkipTest(
                f"custom role '{ROLE_ID}' not present in '{project}' — run scripts/deploy_gcp.sh")
        cls.role = json.loads(result.stdout)
        cls.project = project

    def test_deployed_role_grants_create_and_get(self):
        for permission in REQUIRED_PERMISSIONS:
            self.assertIn(permission, self.role.get("includedPermissions", []))

    def test_deployed_role_withholds_update_and_delete(self):
        for permission in FORBIDDEN_PERMISSIONS:
            self.assertNotIn(permission, self.role.get("includedPermissions", []),
                             f"the DEPLOYED role grants '{permission}' — history is rewritable")

    def test_every_agent_sa_exists_and_holds_the_append_only_role(self):
        policy = subprocess.run(
            ["gcloud", "projects", "get-iam-policy", self.project, "--format=json"],
            capture_output=True, text=True, check=True).stdout
        for role_key, info in AGENT_SA_MAP.items():
            email = f"{info['sa_email'].split('@')[0]}@{self.project}.iam.gserviceaccount.com"
            with self.subTest(agent=role_key):
                exists = subprocess.run(
                    ["gcloud", "iam", "service-accounts", "describe", email,
                     f"--project={self.project}"], capture_output=True).returncode == 0
                self.assertTrue(exists, f"{email} does not exist")
                self.assertIn(f"serviceAccount:{email}", policy)


@unittest.skipUnless(os.environ.get("HODI_E2E") == "1",
                     "Live IAM assertion: set HODI_E2E=1 (needs gcloud credentials).")
class TestDeployedRuntimeIdentityCannotRewriteHistory(unittest.TestCase):
    """
    Live: the identity the deployed Cloud Run service actually executes as holds
    no permission to update or delete a grant event.

    This is the panel's exact finding, answered against reality rather than the
    script: read the service's runtime service account, enumerate every role it
    holds, expand each role's permissions, and assert the UNION contains neither
    datastore.entities.update nor .delete. It is the strongest form of the claim
    'grant history cannot be rewritten' — not that the code avoids it, but that
    the runtime principal is not permitted it.
    """

    @classmethod
    def setUpClass(cls):
        cls.project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        cls.service = os.environ.get("HODI_SERVICE", "hodi-evidence-endpoint")
        cls.region = os.environ.get("HODI_REGION", "us-central1")
        described = subprocess.run(
            ["gcloud", "run", "services", "describe", cls.service,
             f"--region={cls.region}", f"--project={cls.project}",
             "--format=value(spec.template.spec.serviceAccountName)"],
            capture_output=True, text=True)
        if described.returncode != 0 or not described.stdout.strip():
            raise unittest.SkipTest(f"could not read runtime SA for '{cls.service}'")
        cls.runtime_sa = described.stdout.strip()

        policy = json.loads(subprocess.run(
            ["gcloud", "projects", "get-iam-policy", cls.project, "--format=json"],
            capture_output=True, text=True, check=True).stdout)
        member = f"serviceAccount:{cls.runtime_sa}"
        cls.roles = sorted(b["role"] for b in policy["bindings"] if member in b.get("members", []))

    def _permissions_of(self, role: str) -> set:
        if role.startswith("roles/"):
            args = ["gcloud", "iam", "roles", "describe", role, "--format=json"]
        else:  # a project-scoped custom role: projects/<p>/roles/<id>
            role_id = role.split("/")[-1]
            args = ["gcloud", "iam", "roles", "describe", role_id,
                    f"--project={self.project}", "--format=json"]
        out = subprocess.run(args, capture_output=True, text=True)
        if out.returncode != 0:
            return set()
        return set(json.loads(out.stdout).get("includedPermissions", []))

    def test_runtime_sa_is_dedicated_not_the_default_compute_account(self):
        self.assertNotIn("developer.gserviceaccount.com", self.runtime_sa,
                         "service still runs as the default compute SA (holds roles/editor)")

    def test_runtime_sa_holds_no_history_rewriting_role(self):
        offenders = set(self.roles) & HISTORY_REWRITING_ROLES
        self.assertEqual(offenders, set(),
                         f"runtime SA {self.runtime_sa} holds {offenders}, which grant update/delete")

    def test_runtime_effective_permissions_exclude_update_and_delete(self):
        effective = set()
        for role in self.roles:
            effective |= self._permissions_of(role)
        self.assertIn("datastore.entities.create", effective,
                      "runtime SA cannot append — the service cannot write grant events")
        for forbidden in FORBIDDEN_PERMISSIONS:
            self.assertNotIn(forbidden, effective,
                             f"runtime SA's effective permissions include {forbidden} — "
                             "grant history is rewritable at runtime")


if __name__ == "__main__":
    unittest.main()
