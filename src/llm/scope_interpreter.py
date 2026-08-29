"""
src/llm/scope_interpreter.py — natural-language scope interpretation (HOD-301, HOD-311).

THE MODEL INTERPRETS INTENT. THE LATTICE DECIDES PERMISSION.

Gemini's only power here is to produce a typed `Scope` object — nothing else it
outputs can reach the permission decision. The raw model text is parsed as
strict JSON, checked against a closed vocabulary with NO coercion, and only
then instantiated as a `Scope` (whose Pydantic Literal types enforce the
vocabulary a second time). A malformed, out-of-vocabulary, or extra-field
interpretation raises ScopeInterpretationError and the request is rejected —
never guessed at. `permits()` remains the sole authority on permission.
"""

import json
import re
from datetime import datetime
from typing import Optional

from src.schema.scope import Scope
from src.llm.vertex_gemini import VertexGeminiClient, PINNED_INTERPRETER_MODEL

ALLOWED_KEYS = {"use_type", "model_class", "commercial", "attribution_required", "territory"}
USE_TYPES = {"training", "fine_tuning", "rag_retrieval", "human_reference", "synthesis"}
MODEL_CLASSES = {"all_models", "open_weights", "proprietary_frontier"}
TERRITORY_RE = re.compile(r"^(WW|[A-Z]{2})$")

INTERPRETER_PROMPT_TEMPLATE = """You convert a natural-language content-license request into a JSON scope object.

Output ONLY a single JSON object — no prose, no code fences — with EXACTLY these keys:
  "use_type": one of "training" | "fine_tuning" | "rag_retrieval" | "human_reference" | "synthesis"
  "model_class": one of "all_models" | "open_weights" | "proprietary_frontier"
  "commercial": true or false
  "attribution_required": true or false
  "territory": a JSON array of ISO 3166-1 alpha-2 country codes (e.g. ["US","CA"]), or ["WW"] for worldwide

Rules:
- Choose the SINGLE most specific use_type the request describes.
- If the request does not restrict model class, use "all_models".
- If the request does not mention territory, use ["WW"].
- If the request does not mention attribution, use false.
- You decide nothing about whether the request is permitted. You only describe what is being asked.

Request:
{request_text}
"""


class ScopeInterpretationError(Exception):
    """The model's output could not be validated into a Scope. The request is
    rejected; nothing is coerced or guessed."""


def _strict_parse(raw: str) -> dict:
    text = raw.strip()
    # Tolerate a fenced block (formatting), but nothing else around the JSON.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ScopeInterpretationError(f"Model output is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ScopeInterpretationError("Model output is not a JSON object.")
    return obj


def validate_interpretation(obj: dict) -> dict:
    """Closed-vocabulary validation with NO coercion. Extra keys are rejected —
    an interpretation carrying e.g. {"permitted": true} must die here, not be
    ignored quietly."""
    extra = set(obj.keys()) - ALLOWED_KEYS
    if extra:
        raise ScopeInterpretationError(f"Interpretation carries disallowed keys: {sorted(extra)}")
    missing = ALLOWED_KEYS - set(obj.keys())
    if missing:
        raise ScopeInterpretationError(f"Interpretation is missing required keys: {sorted(missing)}")
    if obj["use_type"] not in USE_TYPES:
        raise ScopeInterpretationError(f"use_type '{obj['use_type']}' is outside the closed vocabulary.")
    if obj["model_class"] not in MODEL_CLASSES:
        raise ScopeInterpretationError(f"model_class '{obj['model_class']}' is outside the closed vocabulary.")
    if not isinstance(obj["commercial"], bool):
        raise ScopeInterpretationError("commercial must be a JSON boolean.")
    if not isinstance(obj["attribution_required"], bool):
        raise ScopeInterpretationError("attribution_required must be a JSON boolean.")
    terr = obj["territory"]
    if not isinstance(terr, list) or not terr or not all(isinstance(t, str) and TERRITORY_RE.match(t) for t in terr):
        raise ScopeInterpretationError(f"territory must be a non-empty list of 'WW' or ISO alpha-2 codes; got {terr!r}")
    return obj


class ScopeInterpreter:
    def __init__(self, client: Optional[VertexGeminiClient] = None):
        self.client = client or VertexGeminiClient()
        self.model_id = PINNED_INTERPRETER_MODEL

    def interpret(self, request_text: str, valid_from: datetime) -> Scope:
        """Returns a validated Scope, or raises. There is no third outcome."""
        scope, _ = self.interpret_with_surface(request_text, valid_from)
        return scope

    def interpret_with_surface(self, request_text: str, valid_from: datetime,
                               prefer_live: bool = False):
        """(Scope, surface) — surface is "live" or "cache", from the client.

        A caller that displays the word "live" must display THIS value (HOD-800):
        the guided demo said "read live" over a cache hit, because the label was
        asserted in HTML rather than taken from the run.
        """
        prompt = INTERPRETER_PROMPT_TEMPLATE.format(request_text=request_text)
        raw, surface = self.client.generate_with_surface(
            prompt, model_id=self.model_id, prefer_live=prefer_live)
        fields = validate_interpretation(_strict_parse(raw))
        # Scope's Literal types enforce the vocabulary a second time at
        # construction — belt and braces, both structural.
        return Scope(valid_from=valid_from, **fields), surface
