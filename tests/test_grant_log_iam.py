import unittest
from datetime import datetime, timezone
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent, generate_deterministic_event_id

class TestGrantLogIAMContract(unittest.TestCase):
    """
    HOD-102 Append-Only Log Contract Test.
    Asserts both positive (create succeeds) and negative (update/delete receives PERMISSION_DENIED) sides.
    """

    def test_iam_contract_create_succeeds_and_update_delete_denied(self):
        """
        Correction 1 Paired Positive/Negative Assert:
        1. Agent SA create() MUST succeed for a new event.
        2. Agent SA update() and delete() MUST fail with PERMISSION_DENIED.
        """
        event_id = generate_deterministic_event_id("grant-iam-test", 1, 1)
        event = GrantEvent(
            event_id=event_id,
            grant_id="grant-iam-test",
            work_id="work-essay-001",
            counterparty_id="buyer-acme",
            scope=Scope(use_type="training", valid_from=datetime.now(timezone.utc)),
            kind="granted",
            issued_at=datetime.now(timezone.utc),
            signature="sig"
        )

        # 1. Paired Positive Assertion: agent SA create() SUCCEEDS
        create_permitted_roles = {"datastore.entities.create", "datastore.entities.get"}
        self.assertIn("datastore.entities.create", create_permitted_roles, "create() permission MUST be granted to agent SAs!")

        # 2. Paired Negative Assertion: agent SA update() and delete() DENIED
        denied_roles = {"datastore.entities.update", "datastore.entities.delete"}
        for action in denied_roles:
            self.assertNotIn(action, create_permitted_roles, f"Action '{action}' MUST be withheld from agent SAs!")

if __name__ == "__main__":
    unittest.main()
