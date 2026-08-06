from typing import Dict, Any
from src.agents.base import BaseAgent

class RightsCustodianAgent(BaseAgent):
    """
    Rights Custodian Agent (HOD-310).
    Holds artist identity, registered works, and control proofs.
    CANNOT read buyer terms or evidence.
    """

    def __init__(self):
        super().__init__("rights_custodian")

    def get_registered_works(self) -> Dict[str, Any]:
        """Paired positive: Rights Custodian CAN read works/ collection."""
        return self.access_collection("works")

    def get_artist_identity(self) -> Dict[str, Any]:
        """Paired positive: Rights Custodian CAN read artists/ collection."""
        return self.access_collection("artists")

    def read_buyer_terms(self, counterparty_id: str) -> Dict[str, Any]:
        """Paired negative: Rights Custodian CANNOT read buyer_terms/ collection."""
        return self.access_collection(f"buyer_terms/{counterparty_id}")
