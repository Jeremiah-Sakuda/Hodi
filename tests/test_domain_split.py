"""
tests/test_domain_split.py — the front door delegates domain work and never
performs it (HOD-733).

WHAT THIS SPLIT IS FOR. `conflict_domain_separation` read `in_process_only` for
the life of this project: four roles, one process, one service account holding
credentials for every domain. The policy was real and tested at three altitudes,
and it was still our code promising rather than the infrastructure refusing.

These tests assert the properties that make the deployed split real, offline and
without credentials, so the claim is checkable by anyone who clones the repo:

  1. DEFAULT OFF — with no domain services configured, nothing changes. The
     credential-free demo and the whole offline suite depend on this.
  2. DELEGATION HAPPENS — with services configured, a domain read leaves the
     process instead of touching a database.
  3. THE GRANT LOG NEVER LEAVES — `grants` is shared by every domain identity by
     design, so it must NOT be delegated no matter who asks.
  4. POLICY IS ENFORCED BEFORE THE HOP — a forbidden read is refused locally and
     never becomes a network call, so a denial cannot be turned into a request
     some other service might answer.
  5. NO ONWARD PROXYING — a domain service reads its own database rather than
     calling itself forever.
  6. A DENIAL IS NOT AN EMPTY RESULT — a refusing domain service must raise, not
     return [], or "you may not have it" silently becomes "there is none".
"""

import os
import unittest
from unittest import mock

from src.gateway.domain_client import DomainServiceClient, service_urls, this_service_role
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.schema.iam_policy import (
    AGENT_SA_MAP, DEFAULT_DATABASE_COLLECTIONS, database_for_collection,
)

CUSTODIAN = AGENT_SA_MAP["rights_custodian"]["sa_email"]
NEGOTIATOR = AGENT_SA_MAP["licensing_negotiator"]["sa_email"]
URLS = {"rights_custodian": "https://custodian.example",
        "licensing_negotiator": "https://negotiator.example"}


class EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._prior = {k: os.environ.get(k)
                       for k in ("HODI_DOMAIN_SERVICE_URLS", "HODI_SERVICE_ROLE")}
        os.environ["HODI_OFFLINE"] = "1"

    def tearDown(self):
        for k, v in self._prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class RoutingIsPolicyDerivedTest(EnvIsolated):
    """Where a collection lives is data, not a branch."""

    def test_the_grant_log_stays_in_default_for_every_role(self):
        for role in AGENT_SA_MAP:
            self.assertEqual(database_for_collection(role, "grants"), "(default)",
                             f"{role} would send the shared grant log to a domain database")

    def test_domain_data_routes_to_the_domain_database(self):
        self.assertEqual(database_for_collection("rights_custodian", "works"), "hodi-identity")
        self.assertEqual(database_for_collection("evidence_agent", "crawler_access"),
                         "hodi-evidence")
        self.assertEqual(database_for_collection("licensing_negotiator", "buyer_terms"),
                         "hodi-commercial")

    def test_shared_collections_are_declared_not_guessed(self):
        for shared in ("grants", "revocation_notices", "revocation_outbox"):
            self.assertIn(shared, DEFAULT_DATABASE_COLLECTIONS)


class DefaultOffTest(EnvIsolated):
    """The offline demo must be completely unaffected by this feature existing."""

    def test_no_configuration_means_no_delegation(self):
        os.environ.pop("HODI_DOMAIN_SERVICE_URLS", None)
        self.assertEqual(service_urls(), {})
        self.assertFalse(DomainServiceClient().handles("rights_custodian"))

    def test_an_unparseable_value_disables_rather_than_half_enables(self):
        os.environ["HODI_DOMAIN_SERVICE_URLS"] = "{not json at all"
        self.assertEqual(service_urls(), {})


class DelegationTest(EnvIsolated):
    """With services configured, domain work leaves the process."""

    def _client(self, **kw):
        """
        A domain client that reports the split as deployed, injected rather
        than configured — so this exercises the real delegation path with no
        credentials, no network and no dependence on HODI_OFFLINE.
        """
        c = DomainServiceClient(urls=dict(URLS))
        c.handles = lambda role: role in URLS  # noqa: E731 - deployed-split stand-in
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def test_a_domain_read_is_delegated(self):
        calls = []

        def remote_read(role, collection, filters, session_context):
            calls.append((role, collection))
            return [{"work_id": "from-the-custodian-service"}]

        gw = AgentGateway(offline_reads={"works": [{"work_id": "local-should-not-be-used"}]},
                          domains=self._client(read=remote_read))
        rows = gw.read_collection(calling_sa=CUSTODIAN, calling_role_key="rights_custodian",
                                  target_collection="works")
        self.assertEqual(calls, [("rights_custodian", "works")])
        self.assertEqual(rows, [{"work_id": "from-the-custodian-service"}],
                         "the front door served its own copy instead of the custodian's answer")

    def test_the_grant_log_is_never_delegated(self):
        """
        `grants` is the one collection multiple domain identities legitimately
        reach. Delegating it would put the shared append-only log behind a
        single domain's workload and make the fleet's central record depend on
        one service being up.

        The negotiator is the case that matters: it HAS a domain service and it
        IS permitted the grant log (filtered to its own counterparty), so the
        routing decision cannot be "does this role have a service".
        """
        def must_not_be_called(*a, **k):
            self.fail("the shared grant log was delegated to a domain service")

        gw = AgentGateway(offline_reads={"grants": [{"grant_id": "g1", "counterparty_id": "c1"}]},
                          domains=self._client(read=must_not_be_called))
        rows = gw.read_collection(calling_sa=NEGOTIATOR, calling_role_key="licensing_negotiator",
                                  target_collection="grants",
                                  filters={"counterparty_id": "c1"},
                                  session_context={"counterparty_id": "c1"})
        self.assertEqual(rows, [{"grant_id": "g1", "counterparty_id": "c1"}])

    def test_a_forbidden_read_never_becomes_a_network_call(self):
        """
        Policy is enforced BEFORE the hop. If a denial could travel, a refusal
        here would become a request somewhere else, and the local denial log
        would no longer be the record of what was attempted.
        """
        def must_not_be_called(*a, **k):
            self.fail("a policy-denied read was sent to a domain service")

        gw = AgentGateway(domains=self._client(read=must_not_be_called))
        with self.assertRaises(GatewayPolicyDenial):
            gw.read_collection(calling_sa=NEGOTIATOR, calling_role_key="licensing_negotiator",
                               target_collection="works")

    def test_a_refusing_domain_service_raises_rather_than_returning_empty(self):
        from src.gateway.domain_client import DomainServiceUnavailable

        def refuse(*a, **k):
            raise DomainServiceUnavailable("HTTP 403")

        gw = AgentGateway(domains=self._client(read=refuse))
        with self.assertRaises(DomainServiceUnavailable):
            gw.read_collection(calling_sa=CUSTODIAN, calling_role_key="rights_custodian",
                               target_collection="works")


class NoOnwardProxyingTest(EnvIsolated):
    """A domain service reads its own database; it does not call itself."""

    def test_a_domain_service_does_not_delegate(self):
        os.environ["HODI_DOMAIN_SERVICE_URLS"] = "rights_custodian=https://custodian.example"
        os.environ["HODI_SERVICE_ROLE"] = "rights_custodian"
        self.assertEqual(this_service_role(), "rights_custodian")
        self.assertFalse(DomainServiceClient().handles("rights_custodian"),
                         "the custodian service would proxy to itself forever")


class DeployScriptGrantsNothingThatSpansDatabasesTest(unittest.TestCase):
    """
    The mistake this project already made once, guarded.

    An unconditioned `roles/datastore.viewer` on a domain service account lets
    that identity read EVERY database, and an IAM condition elsewhere narrows
    nothing while a broad grant sits beside it. That is exactly why the
    workload-identity E2E failed its first proof.
    """

    def test_the_domain_deploy_binds_no_unconditioned_datastore_role(self):
        from pathlib import Path
        sh = (Path(__file__).resolve().parent.parent
              / "scripts" / "deploy_domain_services.sh").read_text()
        for line in sh.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "add-iam-policy-binding" in stripped:
                continue
            if "roles/datastore" in stripped and "--condition=None" in stripped:
                self.fail(f"unconditioned datastore grant in the domain deploy: {stripped}")
        # And the conditioned write grant must actually be there.
        self.assertIn("hodiAppendOnlyGrantWriter", sh)
        self.assertIn("resource.name.endsWith('/databases/${DB}')", sh)


if __name__ == "__main__":
    unittest.main()
