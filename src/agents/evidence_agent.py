from typing import Dict, Any
from src.agents.base import BaseAgent

class EvidenceAgent(BaseAgent):
    """
    Evidence Agent (HOD-320).
    Reads crawler access logs and canary hits.
    CANNOT read commercial buyer terms or artist identity.
    """

    def __init__(self):
        super().__init__("evidence_agent")

    def get_crawler_access_logs(self) -> Dict[str, Any]:
        """Paired positive: Evidence Agent CAN read crawler_access/ collection."""
        return self.access_collection("crawler_access")

    def get_canary_records(self) -> Dict[str, Any]:
        """Paired positive: Evidence Agent CAN read canaries/ collection."""
        return self.access_collection("canaries")

    def read_buyer_terms(self, counterparty_id: str) -> Dict[str, Any]:
        """Paired negative: Evidence Agent CANNOT read buyer_terms/ collection."""
        return self.access_collection(f"buyer_terms/{counterparty_id}")

    def read_artist_identity(self) -> Dict[str, Any]:
        """Paired negative: Evidence Agent CANNOT read artist identity."""
        return self.access_collection("artists")
