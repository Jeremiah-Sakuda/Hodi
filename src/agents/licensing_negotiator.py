from typing import Dict, Any, Optional
from src.agents.base import BaseAgent

class LicensingNegotiatorAgent(BaseAgent):
    """
    Licensing Negotiator Agent (HOD-311).
    Negotiates scope requests under confidentiality.
    Scoped strictly to ONE session counterparty_id via IAM & session token.
    CANNOT read artist identity, evidence, or other buyers' terms.
    """

    def __init__(self, session_counterparty_id: str):
        super().__init__("licensing_negotiator")
        self.session_counterparty_id = session_counterparty_id

    def get_session_buyer_terms(self) -> Dict[str, Any]:
        """Paired positive: Negotiator CAN read its own session counterparty's buyer_terms."""
        return self.access_collection(f"buyer_terms/{self.session_counterparty_id}")

    def get_other_buyer_terms(self, other_counterparty_id: str) -> Dict[str, Any]:
        """Paired negative: Negotiator CANNOT read another counterparty's buyer_terms."""
        if other_counterparty_id != self.session_counterparty_id:
            raise PermissionError(
                f"PERMISSION_DENIED: Licensing Negotiator SA '{self.sa_email}' is scoped "
                f"strictly to session counterparty '{self.session_counterparty_id}' and cannot read '{other_counterparty_id}' terms."
            )
        return self.access_collection(f"buyer_terms/{other_counterparty_id}")

    def read_artist_identity(self) -> Dict[str, Any]:
        """Paired negative: Negotiator CANNOT read artist identity."""
        return self.access_collection("artists")
