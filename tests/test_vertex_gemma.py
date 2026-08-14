"""
HOD-301 & HOD-303 test suite — against the REAL runtime modules.

(The previous version of this file tested a self-contained mock client pinning
gemini-1.5 literals that no code path ever called. It was replaced when the
real Vertex client landed; the deeper structural tests for the interpreter live
in tests/test_gemini_interpreter.py.)

Runs offline: HODI_OFFLINE=1 forces cache-only Gemini and the heuristic triage
fallback, so these tests are hermetic and credential-free.
"""

import os
import re
import json
import unittest

from src.llm.vertex_gemini import (
    VertexGeminiClient, GeminiUnavailableError, _cache_key,
    PINNED_INTERPRETER_MODEL, PINNED_GEMMA_TRIAGE_MODEL,
    PINNED_MODELS, TEMPERATURE, CACHE_PATH
)
from src.evidence.gemma_triage import GemmaTriageEngine
from tests.offline_env import force_offline


class TestHod301GeminiClient(unittest.TestCase):
    def setUp(self):
        force_offline(self)
        self.client = VertexGeminiClient()

    def test_pinned_model_ids_are_exact_literals(self):
        """HOD-301: model IDs are pinned literals, never aliases or previews."""
        self.assertEqual(PINNED_INTERPRETER_MODEL, "gemini-3.5-flash")
        self.assertEqual(PINNED_GEMMA_TRIAGE_MODEL, "gemma-4-26b-a4b-it-maas")
        for mid in PINNED_MODELS:
            self.assertNotIn("latest", mid)
            self.assertNotIn("preview", mid)

    def test_every_pinned_model_has_a_call_site(self):
        """A pinned model nobody calls is model-count padding. Each entry in
        PINNED_MODELS must be referenced by code outside src/llm/vertex_gemini.py."""
        import subprocess
        for mid in PINNED_MODELS:
            const = ("PINNED_INTERPRETER_MODEL" if mid == PINNED_INTERPRETER_MODEL
                     else "PINNED_GEMMA_TRIAGE_MODEL")
            hits = subprocess.run(
                ["grep", "-rl", const, "src/", "scripts/"],
                capture_output=True, text=True).stdout.split()
            callers = [h for h in hits if "vertex_gemini.py" not in h]
            self.assertTrue(callers, f"{const} ({mid}) is pinned but called from nowhere")

    def test_temperature_is_zero(self):
        self.assertEqual(TEMPERATURE, 0)

    def test_unpinned_model_rejected(self):
        with self.assertRaises(ValueError):
            self.client.generate("prompt", model_id="gemini-2.5-flash")

    def test_durable_shared_cache_is_committed_and_hit_offline(self):
        """HOD-301: the durable response cache exists, is non-empty, and serves
        recorded responses with zero credentials."""
        self.assertTrue(CACHE_PATH.exists(), "fixtures/gemini_response_cache.json must be committed")
        cache = json.load(open(CACHE_PATH))
        self.assertGreater(len(cache["entries"]), 0)
        key, entry = next(iter(cache["entries"].items()))
        self.assertEqual(key, _cache_key(entry["model_id"], entry["prompt"]))
        self.assertEqual(self.client.generate(entry["prompt"], model_id=entry["model_id"]),
                         entry["response_text"])

    def test_offline_cache_miss_raises(self):
        with self.assertRaises(GeminiUnavailableError):
            self.client.generate("never-cached prompt xyz")


class TestHod303GemmaTriage(unittest.TestCase):
    def setUp(self):
        # Offline: Gemma MaaS raises on cache miss, Ollama is absent, so the
        # heuristic fallback classifies — the NON-LOAD-BEARING property.
        force_offline(self)
        self.engine = GemmaTriageEngine()

    def test_self_deploy_check_traffic_short_circuits(self):
        for ua in ("Python-urllib/3.14", "curl/8.7.1", "Hodi-HealthCheck/1.0",
                   "Hodi-Latency-Test/1.0", "python-requests/2.34.2",
                   "Google-Cloud-Scheduler"):
            with self.subTest(ua=ua):
                self.assertEqual(self.engine.triage_record({"user_agent": ua}), "self_deploy_check")

    def test_any_hodi_prefixed_probe_counts_as_self_traffic(self):
        """The self-traffic list was incomplete three times. A probe named
        Hodi-<anything> must be self-originated the day it is written, without
        anyone remembering to add it."""
        for ua in ("Hodi-Adversarial-Audit/1.0", "Hodi-SomeProbeInventedTomorrow/9.9"):
            with self.subTest(ua=ua):
                self.assertEqual(self.engine.triage_record({"user_agent": ua}), "self_deploy_check")

    def test_the_engine_and_the_audit_agree_on_what_is_self_traffic(self):
        """Two implementations of one rule is how this recurred. They must be
        the same implementation."""
        from src.evidence.self_traffic import is_self_originated
        for ua in ("Hodi-Adversarial-Audit/1.0", "Google-Cloud-Scheduler", "curl/8.7.1",
                   "GPTBot/1.2", "Mozilla/5.0 (compatible)", "MysteryClient/0.1"):
            with self.subTest(ua=ua):
                engine_says_self = self.engine.triage_record({"user_agent": ua}) == "self_deploy_check"
                self.assertEqual(engine_says_self, is_self_originated(ua))

    def test_crawler_signatures_are_generic_vocabulary_only(self):
        """Positioning rule: no real company appears anywhere in the repo.

        Asserted as an ALLOW-LIST of generic crawler vocabulary rather than a
        blocklist of vendor names — a blocklist would have to spell the names it
        forbids, which is the thing being forbidden.
        """
        allowed_words = {"bot", "crawler", "spider", "scraper", "fetcher", "indexer"}
        for pattern in GemmaTriageEngine.THIRD_PARTY_BOT_USER_AGENTS:
            # Strip regex escapes first: \b would otherwise tokenize as a stray "b".
            literal = re.sub(r"\\[a-zA-Z]", " ", pattern.lower())
            words = set(re.findall(r"[a-z]+", literal))
            with self.subTest(pattern=pattern):
                self.assertTrue(
                    words and words <= allowed_words,
                    f"signature {pattern!r} contains non-generic token(s): "
                    f"{sorted(words - allowed_words)}")

    def test_heuristic_fallback_classifies_when_gemma_unavailable(self):
        self.assertEqual(self.engine.triage_record({"user_agent": "Mozilla/5.0 (compatible; GPTBot/1.0)"}), "bot")
        self.assertEqual(self.engine.triage_record({"user_agent": "Mozilla/5.0 (Macintosh) Chrome/120.0"}), "human")
        self.assertEqual(self.engine.triage_record({"user_agent": "MysteryClient/0.1"}), "unknown")

    def test_cached_gemma_maas_classification_used_when_available(self):
        """The committed cache holds a REAL recorded Gemma MaaS response for
        GPTBot/1.2 — offline, the engine serves it from the cache."""
        self.assertEqual(self.engine.triage_record({"user_agent": "GPTBot/1.2"}), "bot")


if __name__ == "__main__":
    unittest.main()
