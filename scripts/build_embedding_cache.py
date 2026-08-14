#!/usr/bin/env python3
"""
scripts/build_embedding_cache.py — record real embeddings into the durable cache
so `make demo` and the offline suite stay credential-free (HOD-320, HOD-350).

Same discipline as fixtures/gemini_response_cache.json: vectors are RECORDED
from real Vertex responses and committed, so the offline path replays genuine
model output rather than a stub. Run after changing FORBIDDEN_CLAIM_ANCHORS or
the probe set.

    python3 scripts/build_embedding_cache.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evidence.semantic_backstop import (
    CACHE_PATH, FORBIDDEN_CLAIM_ANCHORS, PERMITTED_CLAIM_ANCHORS,
    PINNED_EMBEDDING_MODEL, SemanticBackstop)


def main() -> int:
    texts = list(FORBIDDEN_CLAIM_ANCHORS) + list(PERMITTED_CLAIM_ANCHORS)
    try:
        from scripts.measure_lint_coverage import PARAPHRASE_PROBES
        texts += [p if isinstance(p, str) else p[0] for p in PARAPHRASE_PROBES]
    except Exception as exc:
        print(f"  (probe set not loaded: {exc})")

    backstop = SemanticBackstop()
    cache = {"_comment": ("Durable embedding cache (HOD-350). Key = "
                          "'<model>:<lowercased text>'. Recorded from real Vertex AI responses so "
                          "the offline suite and `make demo` replay genuine vectors with zero "
                          "credentials."),
             "model": PINNED_EMBEDDING_MODEL, "entries": {}}
    ok = 0
    for text in texts:
        vec = backstop._fetch_live(text)
        if vec:
            cache["entries"][f"{PINNED_EMBEDDING_MODEL}:{text.strip().lower()}"] = vec
            ok += 1
        print(f"  {'OK ' if vec else 'MISS'} {text[:64]}")
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {ok}/{len(texts)} vectors to {CACHE_PATH.name} "
          f"({CACHE_PATH.stat().st_size // 1024} KB)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
