from typing import Dict, Any, Optional
from src.agents.base import BaseAgent

class LicensingNegotiatorAgent(BaseAgent):
    """
    Licensing Negotiator Agent (HOD-311).
    Negotiates scope requests under confidentiality.
    Scoped strictly to ONE session counterparty_id.
    CANNOT read artist identity, evidence, or other buyers' terms.

    Confidentiality is enforced by POLICY, not by an `if` in this class: every
    read passes `filters` and `session_context` into the IAM policy check, which
    requires the session-scoped filter key and requires its value to match the
    session. An earlier version compared the two ids in a local conditional
    here, which meant the boundary lived off the enforcement path entirely.
    """

    def __init__(self, session_counterparty_id: str):
        super().__init__("licensing_negotiator")
        self.session_counterparty_id = session_counterparty_id

    def _session(self) -> Dict[str, Any]:
        return {"counterparty_id": self.session_counterparty_id}

    def get_session_buyer_terms(self) -> Dict[str, Any]:
        """Paired positive: Negotiator CAN read its own session counterparty's buyer_terms."""
        return self.access_collection(
            "buyer_terms",
            filters={"counterparty_id": self.session_counterparty_id},
            session_context=self._session(),
        )

    def get_other_buyer_terms(self, other_counterparty_id: str) -> Dict[str, Any]:
        """Paired negative: Negotiator CANNOT read another counterparty's buyer_terms.
        The denial comes from the policy check, not from a local comparison."""
        return self.access_collection(
            "buyer_terms",
            filters={"counterparty_id": other_counterparty_id},
            session_context=self._session(),
        )

    def get_unfiltered_buyer_terms(self) -> Dict[str, Any]:
        """Paired negative: an unfiltered collection-wide read is denied — the
        policy requires the session-scoping filter key to be present."""
        return self.access_collection("buyer_terms", session_context=self._session())

    def read_artist_identity(self) -> Dict[str, Any]:
        """Paired negative: Negotiator CANNOT read artist identity."""
        return self.access_collection("artists")
