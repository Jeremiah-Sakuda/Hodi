"""
src/evidence/verbatim_probe.py — the check behind `verbatim_match` (HOD-320).

WHY THIS EXISTS. `EvidenceEngine.process_verbatim_match(prompt, generated_output,
work_id, source_uri)` read NEITHER `prompt` NOR `generated_output`. It built a
constant detail string and emitted an `EvidenceRecord` unconditionally — a
function named after a check that performed none. `process_redistribution` was
worse: its signature carried no content at all, so it could not have checked
anything even in principle. Meanwhile `README.md` stated, inside "What Hodi will
not claim", that "the checking code exists". It did not. That sentence sat among
deliberately exact neighbours (1613 accrued records / 1 crawler match, 4-of-12
lint coverage, `UNSIGNED_PLACEHOLDER`) and borrowed their credibility.

DELIBERATELY NOT A MODEL. "Verbatim" means *exact*. An embedding or an LLM
measures *similarity*, so routing this through a model would let a paraphrase
mint a record typed `verbatim_match` — the same category error as naming a
constant `SIG_REVOKED` and calling it a signature. The check is therefore a
deterministic longest-contiguous-token-run comparison over stdlib `difflib`:
reproducible, offline, credential-free, and explainable to a hostile reader in
one sentence.

WHAT A MATCH DOES AND DOES NOT ESTABLISH. A run of registered text appearing in
a model's output establishes exactly that: the text co-occurs. It does not
establish training-set membership, ingestion, or causation — `EvidenceRecord`
cannot express those, and `claim_limit` restates the boundary on every record.
"""

import difflib
import hashlib
import re
from typing import List, NamedTuple, Optional

# A fixed, published threshold — never tuned per case, because a threshold moved
# to make a particular comparison "hit" is how a matcher becomes a rubber stamp
# with extra steps. Twelve tokens is long enough that ordinary phrase collisions
# ("the model interprets intent") do not qualify.
MIN_VERBATIM_RUN_TOKENS = 12

_PUNCT = re.compile(r"[^\w\s]+")
_WS = re.compile(r"\s+")


def normalize(text: str) -> List[str]:
    """
    Lowercase, strip punctuation, collapse whitespace, split on spaces.

    Published here rather than buried, because the normalization IS part of the
    claim: two texts that differ only in casing or punctuation are treated as
    the same run, and a reader is entitled to know that before believing a
    record.
    """
    if not text:
        return []
    lowered = _PUNCT.sub(" ", text.lower())
    return [t for t in _WS.sub(" ", lowered).strip().split(" ") if t]


class VerbatimRun(NamedTuple):
    """A contiguous token run present in both texts."""
    token_count: int
    passage: str
    passage_sha256: str


def longest_contiguous_run(registered_text: str, candidate_text: str) -> Optional[VerbatimRun]:
    """
    The longest run of tokens appearing contiguously in BOTH texts, or None when
    the longest such run is shorter than MIN_VERBATIM_RUN_TOKENS.

    Returning None is the important half: it is the outcome the previous
    implementation could not produce.
    """
    a, b = normalize(registered_text), normalize(candidate_text)
    if not a or not b:
        return None

    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    block = matcher.find_longest_match(0, len(a), 0, len(b))
    if block.size < MIN_VERBATIM_RUN_TOKENS:
        return None

    passage = " ".join(a[block.a:block.a + block.size])
    return VerbatimRun(
        token_count=block.size,
        passage=passage,
        passage_sha256=hashlib.sha256(passage.encode("utf-8")).hexdigest(),
    )


def contains_canary(canary_string: Optional[str], candidate_text: str) -> bool:
    """
    Exact, case-insensitive containment of a planted canary.

    Canaries are deliberately high-entropy tokens, so containment needs no
    threshold and no fuzz — a canary either survived into the candidate text or
    it did not.
    """
    if not canary_string or not candidate_text:
        return False
    return canary_string.strip().lower() in candidate_text.lower()
