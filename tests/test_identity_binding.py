"""
tests/test_identity_binding.py — the identity the gateway ENFORCES and the
identity it RECORDS must be the same principal (HOD-311, HOD-312).

THE DEFECT. `_enforce(calling_sa, calling_role_key, ...)` decided permission
from `calling_role_key` and used `calling_sa` only to build log text. The two
were never compared, so they could disagree indefinitely — and three of them
did: `revocation-propagator@`, `licensing-negotiator@` and a test's `sender=`
all omitted the `-sa` suffix the policy module declares. Every denial event
those paths produced named a service account that **does not exist in IAM**. An
audit record whose subject cannot be resolved is not an audit record, and this
project's entire evidentiary claim rests on those events.

WHAT THIS DOES AND DOES NOT PROVE — stated because it is the most
over-claimable boundary in the repository:

  DOES: the claimed SA must be the one the policy declares for the claimed
  role, so the enforced identity and the recorded identity cannot drift apart,
  and a stale literal fails immediately instead of silently mislabelling an
  audit trail.

  DOES NOT: authenticate either value. Both still arrive from the caller, so
  in-process code could present a *matching* pair for a role it should not
  hold. Non-forgeable identity requires the role to be derived from a verified
  workload credential — a per-domain service with an OIDC identity token and
  audience validation — which is the four-service split, disclosed as not done.
  This is defence in depth and a drift guard, not zero trust.
"""

import re
import unittest
from pathlib import Path

from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.schema.iam_policy import AGENT_SA_MAP
from tests.offline_env import force_offline

ROOT = Path(__file__).resolve().parent.parent
# PRODUCTION code only. A stale literal in `src/` or `scripts/` mislabels a real
# audit event; a literal inside a test is caught the moment it runs, by the
# runtime binding above — which is exactly how the three shipped drifts were
# found. This file itself must use WRONG literals to prove denial.
SEARCH_DIRS = [ROOT / "src", ROOT / "scripts"]

# A hand-written agent service-account literal, i.e. one not read from the map.
SA_LITERAL = re.compile(
    r'"(rights-custodian|licensing-negotiator|evidence-agent|revocation-propagator|consent-arbiter)'
    r'[a-z-]*@[\w.-]*gserviceaccount\.com"')


class GatewayBindsSaToRoleTest(unittest.TestCase):

    def setUp(self):
        # force_offline RESTORES rather than pops; popping un-declares offline
        # mode for every test that runs afterwards (see tests/offline_env.py).
        force_offline(self)
        self.gateway = AgentGateway()

    def test_declared_pair_is_permitted(self):
        """The paired positive — the binding must not deny correct callers."""
        role = "revocation_propagator"
        self.gateway.read_collection(
            calling_sa=AGENT_SA_MAP[role]["sa_email"],
            calling_role_key=role, target_collection="grants",
            filters={"work_id": "w1"})

    def test_mismatched_sa_is_denied(self):
        """The exact drift that shipped: the '-sa' suffix omitted."""
        role = "revocation_propagator"
        with self.assertRaises(GatewayPolicyDenial) as caught:
            self.gateway.read_collection(
                calling_sa="revocation-propagator@hodi-2026.iam.gserviceaccount.com",
                calling_role_key=role, target_collection="grants",
                filters={"work_id": "w1"})
        self.assertIn("does not match", str(caught.exception))

    def test_borrowing_another_agents_sa_is_denied(self):
        """A caller cannot present one role's key with another role's identity."""
        with self.assertRaises(GatewayPolicyDenial):
            self.gateway.read_collection(
                calling_sa=AGENT_SA_MAP["evidence_agent"]["sa_email"],
                calling_role_key="revocation_propagator",
                target_collection="grants", filters={"work_id": "w1"})

    def test_the_denial_event_names_both_identities(self):
        """The record has to be actionable: which SA was claimed, which was expected."""
        with self.assertRaises(GatewayPolicyDenial) as caught:
            self.gateway.read_collection(
                calling_sa="licensing-negotiator@hodi-2026.iam.gserviceaccount.com",
                calling_role_key="licensing_negotiator",
                target_collection="grants", filters={"counterparty_id": "c1"},
                session_context={"counterparty_id": "c1"})
        reason = caught.exception.denial.reason
        self.assertIn("licensing-negotiator@", reason)
        self.assertIn(AGENT_SA_MAP["licensing_negotiator"]["sa_email"], reason)


class NoHandWrittenServiceAccountLiteralsTest(unittest.TestCase):
    """
    The binding above catches drift at runtime; this catches it at authorship.
    Every agent SA in production code must be read from AGENT_SA_MAP — the same
    module the gateway, the conflict matrix and the provisioning scripts consult
    — so a literal cannot silently disagree with the policy again.
    """

    def test_no_agent_sa_is_written_as_a_literal(self):
        offenders = []
        for base in SEARCH_DIRS:
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts or path.name == "iam_policy.py":
                    continue
                for line_no, line in enumerate(path.read_text().splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("*"):
                        continue  # prose in a comment or docstring may quote one
                    if SA_LITERAL.search(line):
                        offenders.append(f"{path.relative_to(ROOT)}:{line_no}: {stripped[:90]}")
        self.assertEqual(
            offenders, [],
            "agent service accounts must come from AGENT_SA_MAP, never a literal:\n  "
            + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
