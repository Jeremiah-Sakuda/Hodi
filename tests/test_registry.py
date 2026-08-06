import unittest
from src.registry.registry import AgentRegistry, AgentPublication

class TestAgentRegistry(unittest.TestCase):
    """
    Agent Registry Role Discovery Tests (HOD-330 / Correction 5b).
    """

    def setUp(self):
        self.registry = AgentRegistry()
        self.rights_pub = AgentPublication(
            agent_id="agent-rc-001",
            name="Rights Custodian Agent",
            version="1.0.0",
            owning_function="rights_custodian",
            role="rights_custodian",
            scopes=["works.read", "artists.read"]
        )
        self.negotiator_pub = AgentPublication(
            agent_id="agent-ln-001",
            name="Licensing Negotiator Agent",
            version="1.0.0",
            owning_function="licensing_negotiator",
            role="licensing_negotiator",
            scopes=["buyer_terms.read"]
        )
        self.registry.register(self.rights_pub)
        self.registry.register(self.negotiator_pub)

    def test_authorized_discovery_returns_matching_agents(self):
        """Authorized query returns published agent metadata."""
        discovered = self.registry.discover(target_role="rights_custodian", requesting_role_key="licensing_negotiator")
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].agent_id, "agent-rc-001")

    def test_unauthorized_discovery_returns_empty_list(self):
        """
        Correction 5(b) Test:
        An unauthorized role discovering target agents receives [] (EMPTY RESULT),
        avoiding disclosure of agent existence.
        """
        # Evidence agent is not authorized to discover Licensing Negotiator
        discovered = self.registry.discover(target_role="licensing_negotiator", requesting_role_key="evidence_agent")
        self.assertEqual(discovered, [], "Unauthorized discovery query MUST return [] (EMPTY RESULT)!")

if __name__ == "__main__":
    unittest.main()
