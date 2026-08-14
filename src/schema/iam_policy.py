"""
src/schema/iam_policy.py — Single Source of Truth for Agent IAM Permissions & Conflict Boundaries

This module defines the 4-agent Service Account permission matrix and Firestore collection access scopes.
No hand-written documentation exists — docs/architecture/conflict_matrix.md and setup scripts are GENERATED from this data.
"""

from typing import Dict, List, Any

AGENT_SA_MAP: Dict[str, Dict[str, Any]] = {
    "rights_custodian": {
        "sa_email": "rights-custodian-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Rights Custodian",
        "description": "Holds artist identity, registered works, and control proofs. CANNOT read buyer terms or evidence.",
        "conflict_domain": "identity",
        "permitted_collections": ["works", "artists", "control_proofs"],
        "denied_collections": ["buyer_terms", "crawler_access", "canaries", "revocation_notices", "revocation_outbox"]
    },
    "licensing_negotiator": {
        "sa_email": "licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Licensing Negotiator",
        "description": "Negotiates scope requests under confidentiality. Scoped strictly to ONE session counterparty_id.",
        "conflict_domain": "buyer_terms",
        "permitted_collections": [
            # buyer_terms is expressed with a required filter key, NOT as a path
            # template. A path template invited prefix matching, which granted
            # collection-wide reads with no filter at all (see BUILD-LOG 2026-08-07).
            {"collection": "buyer_terms", "required_filter_key": "counterparty_id"},
            "receipts",
            {"collection": "grants", "required_filter_key": "counterparty_id"}
        ],
        "denied_collections": ["artists", "works", "crawler_access", "canaries", "revocation_notices", "revocation_outbox"]
    },
    "evidence_agent": {
        "sa_email": "evidence-agent-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Evidence Agent",
        "description": "Ingests crawler access logs and checks canaries. CANNOT read commercial terms or identity.",
        "conflict_domain": "evidence",
        "permitted_collections": ["crawler_access", "canaries", "evidence_records"],
        "denied_collections": ["artists", "buyer_terms", "grants", "revocation_notices", "revocation_outbox"]
    },
    "revocation_propagator": {
        "sa_email": "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Revocation Propagator",
        "description": "Computes affected grants and emits signed notices/receipts. CANNOT hold artist identity or read buyer terms.",
        "conflict_domain": "revocation",
        # revocation_outbox (HOD-708): the 'notice owed' record committed
        # atomically with the revoked event; delivery discharges it. Same
        # conflict domain as the notices themselves.
        "permitted_collections": ["grants", "revocation_notices", "revocation_outbox"],
        "denied_collections": ["artists", "buyer_terms", "crawler_access", "canaries"]
    },
    "consent_arbiter": {
        "sa_email": "consent-arbiter-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Consent Arbiter",
        "description": ("Adjudicates incidents from TYPED ASSERTIONS ONLY (HOD-704). Holds NONE of the "
                        "four conflict domains: no identity, no buyer terms, no raw evidence, no "
                        "revocation authority — and NO write path to grant history. Its collections are "
                        "the incident record and the containment directives its decisions produce."),
        "conflict_domain": "adjudication",
        "permitted_collections": ["incidents", "incident_assertions", "negotiation_freezes"],
        # Every domain collection is DENIED, explicitly: an adjudicator that
        # could read raw evidence, terms, identity or grants — or rewrite the
        # history it rules on — would be an interested one.
        "denied_collections": ["artists", "works", "control_proofs", "buyer_terms", "grants",
                               "crawler_access", "canaries", "evidence_records",
                               "revocation_notices", "revocation_outbox", "receipts"]
    }
}

# Conflict domain → named Firestore database (HOD-711). Splitting the domains
# across NAMED DATABASES, each with per-SA IAM, moves the conflict boundary
# from "our program promises this agent won't read X" to "this workload
# literally lacks credentials to read X" — a read of a foreign domain fails at
# Google IAM, not at the application layer. `(default)` holds the append-only
# grant log every domain-appropriate identity can reach per the custom role;
# the split databases below are provisioned by scripts/setup_workload_identity.sh
# and are the deployed-separation target, stated as not-yet-executed here.
CONFLICT_DOMAIN_DATABASE: Dict[str, str] = {
    "identity": "hodi-identity",
    "buyer_terms": "hodi-commercial",
    "evidence": "hodi-evidence",
    "revocation": "(default)",
    "adjudication": "hodi-adjudication",
}


def database_for_role(agent_role: str) -> str:
    """The named Firestore database a role's workload identity is scoped to
    (HOD-711). Unknown roles map to '(default)'."""
    info = AGENT_SA_MAP.get(agent_role)
    if not info:
        return "(default)"
    return CONFLICT_DOMAIN_DATABASE.get(info["conflict_domain"], "(default)")


def get_action_permission(agent_role: str, collection_name: str) -> tuple[bool, str | None]:
    """
    Checks if an agent role is authorized to access a given collection.
    Returns a tuple of (is_permitted, required_filter_key).
    If required_filter_key is not None, the gateway MUST enforce that the query is filtered by that key.

    Matching is EXACT on the root collection segment. An earlier version matched
    by prefix (`collection_name.startswith(...)`), which meant a permitted path
    template like "buyer_terms/{counterparty_id}" also permitted an unfiltered
    read of the whole "buyer_terms" collection — the opposite of what the entry
    was written to express. Never reintroduce prefix matching here.

    Denials are consulted FIRST and are absolute: a collection named in
    denied_collections can never be permitted, whatever else the policy says.
    """
    agent_info = AGENT_SA_MAP.get(agent_role)
    if not agent_info:
        return False, None

    root = collection_name.split("/")[0]

    if root in agent_info["denied_collections"] or collection_name in agent_info["denied_collections"]:
        return False, None

    for permitted in agent_info["permitted_collections"]:
        if isinstance(permitted, dict):
            if permitted["collection"] == root:
                return True, permitted.get("required_filter_key")
        elif isinstance(permitted, str):
            if root == permitted:
                return True, None

    return False, None

def is_action_permitted(agent_role: str, collection_name: str) -> bool:
    """Legacy helper for simple boolean checks."""
    permitted, _ = get_action_permission(agent_role, collection_name)
    return permitted
