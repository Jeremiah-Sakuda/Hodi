"""
src/schema/assertion_authority.py — who may CLAIM what (HOD-703).

The single source of truth for per-role assertion authority, in exactly the
pattern of iam_policy.py: declared as data, consulted by the gateway, and
rendered into docs by generation — never hand-written twice. Data access
boundaries answer "who is allowed to KNOW something"; this answers "who is
allowed to CLAIM something", and the two are enforced by the same gateway
with the same structured denials.

The counterparty_advocate is deliberately present here and deliberately
ABSENT from AGENT_SA_MAP: it is the buyer-side voice in an incident — it
may make its one exculpatory assertion, and it holds no data access in
Hodi's domains at all. An authority to speak is not an authority to read.

The consent_arbiter maps to the empty set on purpose: the arbiter concludes
from assertions; it asserts nothing. An adjudicator that could also be a
witness would be an interested one.
"""

from typing import Dict, FrozenSet

ASSERTION_AUTHORITY: Dict[str, FrozenSet[str]] = {
    "evidence_agent": frozenset({"OBSERVED_HTTP_ACCESS"}),
    "licensing_negotiator": frozenset({"GRANT_EXISTED", "GRANT_DID_NOT_EXIST"}),
    "rights_custodian": frozenset({"ACCESS_INCONSISTENT_WITH_SCOPE"}),
    "revocation_propagator": frozenset({"REVOCATION_INITIATED"}),
    "counterparty_advocate": frozenset({"ACCESS_DOES_NOT_ESTABLISH_TRAINING"}),
    "consent_arbiter": frozenset(),
}


def may_assert(role: str, assertion_class: str) -> bool:
    """True iff `role` is authorized to submit `assertion_class`. Unknown
    roles and unknown classes are False — fail closed, never default-permit."""
    return assertion_class in ASSERTION_AUTHORITY.get(role, frozenset())
