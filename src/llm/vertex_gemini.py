"""
src/llm/vertex_gemini.py — the fleet's ONLY model-call surface (HOD-301).

Pinned model ID literals, temperature 0, and a durable shared response cache.

Model availability was probed empirically on 2026-08-07 (see docs/FINDINGS.md):
`gemini-3.5-flash` returns HTTP 200 on the `global`
Vertex AI endpoint for this project; `gemini-3.5-pro` does not exist in the
publisher catalog and 404s in every probed location; the pro-class 3.x IDs are
all previews, which roll — judging runs to Oct 1, so previews are excluded.
`gemma-4-26b-a4b-it-maas` (serverless Gemma) returns HTTP 200 on `global`.

The cache (fixtures/gemini_response_cache.json) is committed so `make demo`
replays recorded model responses with zero credentials and byte determinism.
With HODI_OFFLINE=1 the client is cache-only and NEVER performs network I/O.
"""

import os
import json
import hashlib
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

# Pinned literals — never aliases, never previews (HOD-301).
PINNED_INTERPRETER_MODEL = "gemini-3.5-flash"
PINNED_GEMMA_TRIAGE_MODEL = "gemma-4-26b-a4b-it-maas"
# Only models an execution path actually calls belong here. `gemini-3.5-flash-lite`
# was pinned and asserted in tests while being called from nowhere — log triage is
# Gemma's tier. A pinned constant with no call site reads as model-count padding.
PINNED_MODELS = {PINNED_INTERPRETER_MODEL, PINNED_GEMMA_TRIAGE_MODEL}

VERTEX_LOCATION = "global"
TEMPERATURE = 0

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "gemini_response_cache.json"


class GeminiUnavailableError(Exception):
    """Raised when a response is needed, not cached, and the client is offline
    or the network call fails. Callers must degrade explicitly — never guess."""


def _cache_key(model_id: str, prompt: str) -> str:
    return hashlib.sha256(f"{model_id}:t{TEMPERATURE}:{prompt}".encode("utf-8")).hexdigest()


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {"_comment": "Durable shared Gemini response cache (HOD-301). Key = sha256(model:t0:prompt). Recorded from real Vertex AI responses; `make demo` replays these with zero credentials.", "entries": {}}


def _get_token() -> str:
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception:
        return subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()


class VertexGeminiClient:
    """
    Thin REST client for Vertex AI generateContent.
    - model_id MUST be one of the pinned literals, or ValueError.
    - temperature is ALWAYS 0.
    - every response is served from / recorded to the durable cache.
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "hodi-2026")
        self._cache = _load_cache()

    def generate(self, prompt: str, model_id: str = PINNED_INTERPRETER_MODEL) -> str:
        text, _ = self.generate_with_surface(prompt, model_id)
        return text

    def generate_with_surface(self, prompt: str, model_id: str = PINNED_INTERPRETER_MODEL,
                              prefer_live: bool = False):
        """Returns (response_text, surface) where surface is "live" or "cache".

        Default order is cache-first — the credential-free demo's contract.
        `prefer_live=True` inverts it: try Vertex FIRST, fall back to the cache
        only if the live call fails. Added for HOD-800: the guided walkthrough's
        page said "read live" while this client answered its fixed request from
        the committed cache — a true integration wearing a stronger label than
        the run it labelled. A caller that shows the word "live" must take the
        surface from THIS return value, never assert it. Under HODI_OFFLINE=1
        `prefer_live` still never touches the network — offline is a promise,
        not a preference.
        """
        if model_id not in PINNED_MODELS:
            raise ValueError(f"Model ID '{model_id}' is not a pinned literal. Pinned: {sorted(PINNED_MODELS)}")

        key = _cache_key(model_id, prompt)
        offline = os.environ.get("HODI_OFFLINE") == "1"

        if prefer_live and not offline:
            try:
                return self._record(key, model_id, prompt, self._call_vertex(prompt, model_id)), "live"
            except Exception:  # noqa: BLE001 — fall back to the recorded response, labelled as such
                if key in self._cache["entries"]:
                    return self._cache["entries"][key]["response_text"], "cache"
                raise

        if key in self._cache["entries"]:
            return self._cache["entries"][key]["response_text"], "cache"

        if offline:
            raise GeminiUnavailableError(
                f"HODI_OFFLINE=1 and no cached response for this prompt under '{model_id}'. "
                "The offline path never calls the network."
            )

        return self._record(key, model_id, prompt, self._call_vertex(prompt, model_id)), "live"

    def _record(self, key: str, model_id: str, prompt: str, text: str) -> str:

        if os.environ.get("HODI_CACHE_WRITE") == "1":
            self._cache["entries"][key] = {"model_id": model_id, "prompt": prompt, "response_text": text}
            with open(CACHE_PATH, "w") as f:
                json.dump(self._cache, f, indent=2, sort_keys=True)
                f.write("\n")
        return text

    def _call_vertex(self, prompt: str, model_id: str) -> str:
        url = (f"https://aiplatform.googleapis.com/v1/projects/{self.project_id}"
               f"/locations/{VERTEX_LOCATION}/publishers/google/models/{model_id}:generateContent")
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": TEMPERATURE}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {_get_token()}",
            "Content-Type": "application/json",
            "x-goog-user-project": self.project_id,
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except GeminiUnavailableError:
            raise
        except Exception as e:
            raise GeminiUnavailableError(f"Vertex AI call to '{model_id}' failed: {e}") from e
