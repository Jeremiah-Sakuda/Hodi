"""
src/schema/lattice.py — The Partial Order Declared as Data (HOD-104)

This module defines the scope lattice partial order relations strictly as DATA structures.
No branching logic or conditionals define the containment relationships.
"""

from typing import Dict, List, Set, Tuple

# Use-Type Partial Order (Hasse Diagram / Transitive Closure)
# Parent use-type mapped to the set of contained child use-types:
# training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference
# synthesis is incomparable to all of the above
USE_TYPE_CONTAINMENT: Dict[str, Set[str]] = {
    "training": {"training", "fine_tuning", "rag_retrieval", "human_reference"},
    "fine_tuning": {"fine_tuning", "rag_retrieval", "human_reference"},
    "rag_retrieval": {"rag_retrieval", "human_reference"},
    "human_reference": {"human_reference"},
    "synthesis": {"synthesis"}
}

# Model Class Partial Order
# all_models ⊃ open_weights, all_models ⊃ proprietary_frontier
MODEL_CLASS_CONTAINMENT: Dict[str, Set[str]] = {
    "all_models": {"all_models", "open_weights", "proprietary_frontier"},
    "open_weights": {"open_weights"},
    "proprietary_frontier": {"proprietary_frontier"}
}

def is_use_type_contained(granted_use_type: str, requested_use_type: str) -> bool:
    """Returns True if granted_use_type contains requested_use_type via lattice data lookup."""
    contained_set = USE_TYPE_CONTAINMENT.get(granted_use_type, set())
    return requested_use_type in contained_set

def is_model_class_contained(granted_class: str, requested_class: str) -> bool:
    """Returns True if granted_class contains requested_class via lattice data lookup."""
    contained_set = MODEL_CLASS_CONTAINMENT.get(granted_class, set())
    return requested_class in contained_set


def use_type_covers(use_type: str) -> List[str]:
    """
    The COVERING RELATION (Hasse edges) derived from the transitive closure above.

    `y` is covered by `x` when y is contained in x, y != x, and no intermediate z
    sits between them. Derived rather than declared so there is exactly one place
    the partial order lives.
    """
    closure = USE_TYPE_CONTAINMENT.get(use_type, set()) - {use_type}
    covers = []
    for candidate in closure:
        intermediates = [
            z for z in closure
            if z not in (candidate, use_type) and candidate in USE_TYPE_CONTAINMENT.get(z, set())
        ]
        if not intermediates:
            covers.append(candidate)
    return sorted(covers)


def use_type_derivation_chain(revoked_use_type: str) -> List[Tuple[str, str, str]]:
    """
    Returns the derivation of every use-type a revocation of `revoked_use_type`
    reaches, as (scope, parent, reason) walking the covering relation.

    `RevocationPropagatorAgent` used to hard-code this as an if/elif ladder
    enumerating the chain for 'training', 'fine_tuning' and 'rag_retrieval' —
    a SECOND source of truth for the partial order, and a correctness risk
    rather than a style one, because the cascade computes downstream scopes
    from it. Adding a use-type to the lattice would have silently produced an
    incomplete cascade. It is now derived from the data (HOD-104).
    """
    chain: List[Tuple[str, str, str]] = [
        (revoked_use_type, revoked_use_type, "Directly revoked")
    ]
    seen = {revoked_use_type}
    frontier = [revoked_use_type]
    while frontier:
        parent = frontier.pop(0)
        for child in use_type_covers(parent):
            if child in seen:
                continue
            seen.add(child)
            chain.append((child, parent, f"{parent} ⊃ {child}"))
            frontier.append(child)
    return chain
