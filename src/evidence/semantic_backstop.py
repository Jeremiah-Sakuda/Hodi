"""
src/evidence/semantic_backstop.py — an embedding backstop behind the overclaim
lint (HOD-320, HOD-350).

THE DISCLOSED WEAKNESS THIS ADDRESSES. `OverclaimLint` is a list of nine regexes.
Its paraphrase coverage is measured, published, and poor: against a 12-paraphrase
probe set seeded from phrasings it was deliberately not written against, **it
rejects 4**. "Disregard everything that preceded this" is the same claim as
"trained on" and matches nothing. The README already says the schema is the
invariant and the lint is a backstop — this makes the backstop less bad without
pretending it is the guarantee.

WHY A MODEL IS SAFE *HERE* AND NOWHERE ELSE IN HODI. The rule is that a model
never decides rights. This model decides nothing about rights, about grants, or
about evidence classification. It inspects text **Hodi itself is about to emit**
and can only ever ADD a refusal:

    lint  = regex_reject  OR  semantic_reject

It is monotonic in strictness. There is no input for which enabling the backstop
PERMITS text the regexes would have rejected — `test_semantic_backstop.py`
asserts exactly that. So the failure mode of a wrong embedding is a false
refusal (Hodi declines to emit a notice and falls back to the linted
deterministic template), never a false permission. A system that fails toward
silence about a claim it cannot verify is failing in the right direction.

WHAT IT IS NOT. It is not a general paraphrase detector, it does not make the
lint sound, and it does not change the structural guarantee — `EvidenceRecord`
still has no field capable of expressing training-set membership, and that
remains the only thing standing between Hodi and the claim. Coverage stays
measured and published rather than asserted: `make lint-coverage` regenerates
the figure against the same probe set, and `make check-docs` fails the build if
the README drifts from it.

OFFLINE. Embeddings are fetched through the same durable committed cache as
every other model call (`fixtures/gemini_response_cache.json` semantics), so
`make demo` stays credential-free. With `HODI_OFFLINE=1` and no cached vector,
the backstop DISABLES ITSELF and the regex verdict stands alone — it never
blocks the offline path and never silently becomes the sole authority.
"""

import json
import math
import os
from pathlib import Path
from typing import List, Optional

# Pinned exactly like every other model ID in this project. Probed reachable on
# 2026-08-14 (HTTP 200, publisher `:predict`); `text-embedding-005` also
# returned 200 and is the documented fallback if this ID stops resolving.
PINNED_EMBEDDING_MODEL = "gemini-embedding-001"

# Cosine similarity at or above which a candidate is treated as an overclaim
# paraphrase. Fixed and published — a threshold tuned per case is how a
# backstop becomes theatre. Chosen so the measured probe set improves without
# any known-good notice text being refused; both directions are asserted in
# tests/test_semantic_backstop.py.
SIMILARITY_THRESHOLD = 0.72

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "embedding_cache.json"

# The canonical claims Hodi must never make, in plain language. These are the
# ANCHORS a candidate is compared against — not patterns, so a paraphrase that
# evades every regex can still land near one of them.
FORBIDDEN_CLAIM_ANCHORS = [
    "this work was in the model's training data",
    "the model was trained on your work",
    "we proved the model ingested this work",
    "your content is inside the model's weights",
    "this proves the model memorized the work",
    "the model learned from this specific work",
]

# The honest phrasings Hodi legitimately emits. These exist because embeddings
# handle NEGATION poorly: "this revocation does not un-train the model" DENIES
# the forbidden claim, yet sits close to it in embedding space, and a one-sided
# threshold rejected it. That is not a hypothetical — every drafted revocation
# notice is REQUIRED to contain the phrase "does not un-train"
# (src/llm/notice_drafter.py), so a naive backstop would refuse the very text
# the system is built to produce.
#
# So the decision is NEAREST-ANCHOR, not a one-sided cut: a candidate is
# refused only when it is close to a forbidden claim AND closer to it than to
# anything Hodi is supposed to say.
PERMITTED_CLAIM_ANCHORS = [
    "this grant is terminated; the revocation does not un-train any model",
    "this record does not assert training-set membership",
    "crawler access was observed at the evidence endpoint",
    "a contiguous run of registered text appears in the observed output; co-occurrence only",
    "the registered work was observed at a third-party mirror uri",
    "the requested scope is not permitted by any active grant",
    "training-set membership is not determinable and is not claimed",
]


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH) as f:
                return json.load(f)
        except ValueError:
            return {"entries": {}}
    return {"entries": {}}


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


class SemanticBackstop:
    """Embedding-based paraphrase backstop. Adds refusals; never grants."""

    def __init__(self, threshold: float = SIMILARITY_THRESHOLD):
        self.threshold = threshold
        self._cache = _load_cache()
        # Per-instance memo. Without it every lint_text() re-embedded all six
        # anchors — seven model calls per linted sentence, which turned a 20s
        # offline suite into 66s the first time this was wired in.
        self._memo: dict = {}

    def _embed(self, text: str) -> Optional[List[float]]:
        """Cached vector, else a live call, else None (backstop disables itself)."""
        key = f"{PINNED_EMBEDDING_MODEL}:{text.strip().lower()}"
        if key in self._memo:
            return self._memo[key]
        cached = self._cache.get("entries", {}).get(key)
        if cached:
            self._memo[key] = cached
            return cached
        if os.environ.get("HODI_OFFLINE") == "1":
            return None
        try:
            vector = self._fetch_live(text)
            self._memo[key] = vector
            return vector
        except Exception:
            self._memo[key] = None
            # Non-load-bearing by construction: an unreachable embedding surface
            # leaves the regex verdict standing, exactly as before this module.
            return None

    def _fetch_live(self, text: str) -> Optional[List[float]]:
        import subprocess
        import urllib.request

        project = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
        ).decode().strip()
        url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/"
               f"publishers/google/models/{PINNED_EMBEDDING_MODEL}:predict")
        body = json.dumps({"instances": [{"content": text}]}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        preds = data.get("predictions") or []
        if not preds:
            return None
        emb = preds[0].get("embeddings") or {}
        return emb.get("values") or preds[0].get("textEmbedding")

    def _nearest(self, vector: List[float], anchors: List[str]):
        best_score, best_anchor = 0.0, None
        for anchor in anchors:
            anchor_vec = self._embed(anchor)
            if not anchor_vec:
                continue
            score = _cosine(vector, anchor_vec)
            if score > best_score:
                best_score, best_anchor = score, anchor
        return best_score, best_anchor

    def is_semantic_overclaim(self, text: str) -> Optional[str]:
        """
        Returns the forbidden anchor a candidate is nearest to, or None.

        A candidate is refused only when BOTH hold:
          1. it is at least SIMILARITY_THRESHOLD from some forbidden claim, and
          2. it is closer to that forbidden claim than to anything Hodi is
             legitimately supposed to say (PERMITTED_CLAIM_ANCHORS).

        Condition 2 is what makes negation survivable: "the revocation does not
        un-train any model" is near the forbidden claim in embedding space, but
        nearer still to the permitted phrasing, so it passes.

        None is also returned when no vector is available — an unavailable model
        must not become an implicit accusation, and must not block the offline
        path.
        """
        vector = self._embed(text)
        if not vector:
            return None
        forbidden_score, forbidden_anchor = self._nearest(vector, FORBIDDEN_CLAIM_ANCHORS)
        if forbidden_anchor is None or forbidden_score < self.threshold:
            return None
        permitted_score, _ = self._nearest(vector, PERMITTED_CLAIM_ANCHORS)
        if permitted_score >= forbidden_score:
            return None
        return forbidden_anchor
