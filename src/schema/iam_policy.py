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
        "denied_collections": ["buyer_terms", "crawler_access", "canaries", "revocation_notices"]
    },
    "licensing_negotiator": {
        "sa_email": "licensing-negotiator-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Licensing Negotiator",
        "description": "Negotiates scope requests under confidentiality. Scoped strictly to ONE session counterparty_id.",
        "conflict_domain": "buyer_terms",
        "permitted_collections": ["buyer_terms/{counterparty_id}", "receipts"],
        "denied_collections": ["artists", "works", "crawler_access", "canaries", "revocation_notices"]
    },
    "evidence_agent": {
        "sa_email": "evidence-agent-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Evidence Agent",
        "description": "Ingests crawler access logs and checks canaries. CANNOT read commercial terms or identity.",
        "conflict_domain": "evidence",
        "permitted_collections": ["crawler_access", "canaries", "evidence_records"],
        "denied_collections": ["artists", "buyer_terms", "grants", "revocation_notices"]
    },
    "revocation_propagator": {
        "sa_email": "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
        "role_name": "Revocation Propagator",
        "description": "Computes affected grants and emits signed notices/receipts. CANNOT hold artist identity or read buyer terms.",
        "conflict_domain": "revocation",
        "permitted_collections": ["grants", "revocation_notices"],
        "denied_collections": ["artists", "buyer_terms", "crawler_access", "canaries"]
    }
}

def is_action_permitted(agent_role: str, collection_name: str) -> bool:
    """Checks if an agent role is authorized to access a given collection."""
    agent_info = AGENT_SA_MAP.get(agent_role)
    if not agent_info:
        return False
    
    # Check exact match or prefix match (e.g. buyer_terms/{counterparty_id})
    for permitted in agent_info["permitted_collections"]:
        if collection_name == permitted or collection_name.startswith(permitted.split("/{")[0]):
            return True
    return False
