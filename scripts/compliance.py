#!/usr/bin/env python3
import sys
import re
from pathlib import Path

def main():
    prd_path = Path("docs/PRD.md")
    if not prd_path.exists():
        print("Error: docs/PRD.md not found.", file=sys.stderr)
        sys.exit(1)

    text = prd_path.read_text(encoding="utf-8")
    has_error = False

    # 1. Check for range notation (e.g., HOD-601–608, HOD-601-608, HOD-601..608)
    range_pattern = r'HOD-\d{3}\s*[\u2013\u2014\-\.]{1,2}\s*\d{3}'
    ranges_found = re.findall(range_pattern, text)
    if ranges_found:
        print(f"FAILED: Range notation detected in docs/PRD.md: {ranges_found}", file=sys.stderr)
        has_error = True

    # 2. Parse sections
    # Split text into sections by "## "
    sections = re.split(r'\n(?=##\s+)', text)
    
    sec2_text = ""
    sec4_text = ""
    prose_texts = []

    for sec in sections:
        if sec.startswith("## 2."):
            sec2_text = sec
        elif sec.startswith("## 4."):
            sec4_text = sec
        else:
            prose_texts.append(sec)

    prose_combined = "\n".join(prose_texts)

    # 3. Extract HOD-### IDs
    id_pattern = r'HOD-\d{3}'

    sec4_ids = set(re.findall(id_pattern, sec4_text))
    sec2_ids = set(re.findall(id_pattern, sec2_text))
    prose_ids = set(re.findall(id_pattern, prose_combined))

    print(f"Extracted {len(sec4_ids)} requirement IDs from Section 4.")
    print(f"Extracted {len(sec2_ids)} requirement IDs from Section 2 matrix.")
    print(f"Extracted {len(prose_ids)} requirement IDs from PRD prose.")

    # 4. Check for orphans and diffs
    # Matrix vs Sec 4
    matrix_orphans = sec2_ids - sec4_ids
    if matrix_orphans:
        print(f"FAILED: Requirement IDs in Section 2 matrix not defined in Section 4: {sorted(matrix_orphans)}", file=sys.stderr)
        has_error = True

    # Sec 4 vs Matrix
    unmapped_sec4 = sec4_ids - sec2_ids
    if unmapped_sec4:
        print(f"FAILED: Requirement IDs in Section 4 not present in Section 2 matrix: {sorted(unmapped_sec4)}", file=sys.stderr)
        has_error = True

    # Prose orphans
    prose_orphans = prose_ids - sec4_ids
    if prose_orphans:
        print(f"FAILED: Requirement IDs in prose not defined in Section 4: {sorted(prose_orphans)}", file=sys.stderr)
        has_error = True

    if has_error:
        print("\nCompliance verification FAILED.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nCompliance verification PASSED: {len(sec4_ids)} requirements verified across §4, §2 matrix, and prose. Zero orphans or range notations.")
        sys.exit(0)

if __name__ == "__main__":
    main()
