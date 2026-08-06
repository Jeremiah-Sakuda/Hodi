#!/usr/bin/env python3
"""
scripts/verify_scopes.py — Scope Lattice & Containment Verification (HOD-104, HOD-106)

Contract for `make verify-scopes`:
1. Prints the scope lattice table declared as data in src/schema/lattice.py.
2. Runs the >=40-case containment truth table test suite in CI.
"""

import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema.lattice import USE_TYPE_CONTAINMENT, MODEL_CLASS_CONTAINMENT

def print_lattice_table():
    print("================================================================================")
    print("                       HODI SCOPE LATTICE PARTIAL ORDER                        ")
    print("================================================================================")
    print("\n1. USE-TYPE CONTAINMENT HIERARCHY (training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference)")
    print("   Declared as DATA in src/schema/lattice.py:\n")
    print(f"   {'Granted Use-Type':<20} | {'Contained Use-Types (Subset Permitted)':<50}")
    print("   " + "-" * 75)
    for parent, children in USE_TYPE_CONTAINMENT.items():
        children_str = ", ".join(sorted(list(children)))
        print(f"   {parent:<20} | {children_str:<50}")

    print("\n2. MODEL-CLASS CONTAINMENT HIERARCHY (all_models ⊃ open_weights, proprietary_frontier)")
    print("   Declared as DATA in src/schema/lattice.py:\n")
    print(f"   {'Granted Model-Class':<20} | {'Contained Model-Classes':<50}")
    print("   " + "-" * 75)
    for parent, children in MODEL_CLASS_CONTAINMENT.items():
        children_str = ", ".join(sorted(list(children)))
        print(f"   {parent:<20} | {children_str:<50}")
    print("\n================================================================================\n")

def run_truth_table_tests():
    print("Running >=40-case Scope Containment Truth Table Test Suite...\n")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_scope_containment")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

def main():
    print_lattice_table()
    success = run_truth_table_tests()
    if not success:
        print("\nScope containment truth table verification FAILED.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nScope containment truth table verification PASSED cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()
