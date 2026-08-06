"""
src/schema/lattice.py — The Partial Order Declared as Data (HOD-104)

This module defines the scope lattice partial order relations strictly as DATA structures.
No branching logic or conditionals define the containment relationships.
"""

from typing import Dict, Set

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
