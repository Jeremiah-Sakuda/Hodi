from typing import Dict, Any
from src.agents.base import BaseAgent

class RevocationPropagatorAgent(BaseAgent):
    """
    Revocation Propagator Agent (HOD-350).
    Computes affected grants and emits signed notices + receipts.
    Correction 3: Receives an opaque counterparty_id and delegates delivery through Gateway.
    NEVER reads buyer_terms/ or holds artist identity (artists/).
    """

    def __init__(self):
        super().__init__("revocation_propagator")

    def write_revocation_notice(self, notice_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Paired positive: Revocation Propagator CAN write revocation_notices/ collection."""
        res = self.access_collection("revocation_notices")
        res["notice_id"] = notice_payload.get("notice_id", "notice-001")
        res["receipt"] = f"rcpt-sig-{res['notice_id']}"
        return res

    def get_grants(self) -> Dict[str, Any]:
        """Paired positive: Revocation Propagator CAN read grants/ collection."""
        return self.access_collection("grants")

    def read_buyer_terms(self, counterparty_id: str) -> Dict[str, Any]:
        """Paired negative (Correction 3): Propagator CANNOT read buyer_terms/ collection."""
        return self.access_collection(f"buyer_terms/{counterparty_id}")

    def read_artist_identity(self) -> Dict[str, Any]:
        """Paired negative: Propagator CANNOT read artist identity (artists/)."""
        return self.access_collection("artists")
