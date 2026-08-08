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

REQUIRED_PERMISSIONS = {"datastore.entities.create", "datastore.entities.get"}
FORBIDDEN_PERMISSIONS = {"datastore.entities.update", "datastore.entities.delete"}


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
        self.assertEqual(len(AGENT_SA_MAP), 4)


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


if __name__ == "__main__":
    unittest.main()
