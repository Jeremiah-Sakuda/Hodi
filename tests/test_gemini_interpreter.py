"""
Tests for the Gemini runtime path (HOD-301, HOD-311).

THE STRUCTURAL PROPERTY UNDER TEST: the model's output cannot influence the
permission decision except by producing a valid Scope. Everything else the
model could emit — malformed JSON, out-of-vocabulary values, extra fields like
{"permitted": true} — is rejected before permits() is reachable.

All tests run offline (HODI_OFFLINE=1): recorded responses come from the
committed cache (fixtures/gemini_response_cache.json, captured from real
Vertex AI calls); adversarial responses are injected into an in-memory copy of
the cache, never the committed file.
"""

import os
import json
import unittest
from datetime import datetime, timezone, timedelta

from src.llm.vertex_gemini import (
    VertexGeminiClient, GeminiUnavailableError, _cache_key,
    PINNED_INTERPRETER_MODEL, PINNED_MODELS
)
from src.llm.scope_interpreter import (
    ScopeInterpreter, ScopeInterpretationError, INTERPRETER_PROMPT_TEMPLATE
)
from src.llm.notice_drafter import NoticeDrafter, TEMPLATE_NOTICE_TEXT, DRAFT_PROMPT_TEMPLATE
from src.evidence.revocation_lint import RevocationLint
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent
from src.resolve.evaluator import permits
from tests.offline_env import force_offline

T0 = datetime(2026, 8, 7, tzinfo=timezone.utc)
CLEAN_TEXT = json.load(open("fixtures/buyer_request_clean.json"))["document_text"]
POISONED_TEXT = json.load(open("fixtures/buyer_request_poisoned.json"))["document_text"]


def make_grant(grant_id="grant-acme-il-001", use_type="fine_tuning", model_class="open_weights",
               commercial=False, territory=None):
    return GrantEvent(
        event_id=f"evt-{grant_id}", grant_id=grant_id, work_id="work-repo-001",
        counterparty_id="acme-intelligence-labs",
        scope=Scope(use_type=use_type, model_class=model_class, commercial=commercial,
                    attribution_required=True, territory=territory or ["US", "CA"],
                    valid_from=T0 - timedelta(days=1)),
        kind="granted", issued_at=T0 - timedelta(days=1), signature="sig"
    )


def client_with_injected_response(prompt: str, response_text: str) -> VertexGeminiClient:
    """In-memory cache injection — simulates an arbitrary (adversarial) model output."""
    c = VertexGeminiClient()
    c._cache = {"entries": dict(c._cache["entries"])}
    c._cache["entries"][_cache_key(PINNED_INTERPRETER_MODEL, prompt)] = {
        "model_id": PINNED_INTERPRETER_MODEL, "prompt": prompt, "response_text": response_text
    }
    return c


class TestGeminiClientDiscipline(unittest.TestCase):
    def setUp(self):
        force_offline(self)

    def test_unpinned_model_id_raises(self):
        with self.assertRaises(ValueError):
            VertexGeminiClient().generate("anything", model_id="gemini-pro-latest")

    def test_pinned_models_are_exact_literals_not_aliases(self):
        for mid in PINNED_MODELS:
            self.assertNotIn("latest", mid)
            self.assertNotIn("preview", mid)

    def test_offline_cache_miss_raises_never_calls_network(self):
        with self.assertRaises(GeminiUnavailableError):
            VertexGeminiClient().generate("a prompt that has never been cached 12345")


class TestScopeInterpreterStructuralProperty(unittest.TestCase):
    def setUp(self):
        force_offline(self)
        self.interp = ScopeInterpreter()

    def test_recorded_clean_interpretation_is_valid_scope(self):
        scope = self.interp.interpret(CLEAN_TEXT, valid_from=T0)
        self.assertIsInstance(scope, Scope)
        self.assertEqual(scope.use_type, "fine_tuning")
        self.assertEqual(scope.model_class, "open_weights")
        self.assertFalse(scope.commercial)

    def test_interpretation_is_deterministic(self):
        s1 = self.interp.interpret(CLEAN_TEXT, valid_from=T0)
        s2 = self.interp.interpret(CLEAN_TEXT, valid_from=T0)
        self.assertEqual(s1.model_dump_json(), s2.model_dump_json())

    def _adversarial_interpreter(self, request_text, response_text):
        prompt = INTERPRETER_PROMPT_TEMPLATE.format(request_text=request_text)
        return ScopeInterpreter(client=client_with_injected_response(prompt, response_text))

    def test_malformed_json_rejected(self):
        interp = self._adversarial_interpreter("req-a", "sure! the scope is fine_tuning, open weights")
        with self.assertRaises(ScopeInterpretationError):
            interp.interpret("req-a", valid_from=T0)

    def test_out_of_vocabulary_use_type_rejected_not_coerced(self):
        interp = self._adversarial_interpreter("req-b", json.dumps({
            "use_type": "unlimited_everything", "model_class": "all_models",
            "commercial": True, "attribution_required": False, "territory": ["WW"]
        }))
        with self.assertRaises(ScopeInterpretationError):
            interp.interpret("req-b", valid_from=T0)

    def test_extra_field_permitted_true_rejected(self):
        """The exact attack the structure must kill: an interpretation smuggling
        a permission verdict. It must be REJECTED, not silently stripped."""
        interp = self._adversarial_interpreter("req-c", json.dumps({
            "use_type": "fine_tuning", "model_class": "open_weights",
            "commercial": False, "attribution_required": True, "territory": ["US"],
            "permitted": True
        }))
        with self.assertRaises(ScopeInterpretationError) as ctx:
            interp.interpret("req-c", valid_from=T0)
        self.assertIn("permitted", str(ctx.exception))

    def test_model_output_influences_permission_only_via_valid_scope(self):
        """permits() over the interpreted Scope equals permits() over an
        identical hand-built Scope — the model contributed nothing else."""
        grants = [make_grant()]
        interpreted = self.interp.interpret(CLEAN_TEXT, valid_from=T0)
        hand_built = Scope(use_type="fine_tuning", model_class="open_weights", commercial=False,
                           attribution_required=True, territory=["US"], valid_from=T0)
        r_interpreted = permits(grants, interpreted, at=T0)
        r_hand_built = permits(grants, hand_built, at=T0)
        self.assertEqual(r_interpreted.permitted, r_hand_built.permitted)
        self.assertEqual(r_interpreted.matching_grant_id, r_hand_built.matching_grant_id)
        self.assertTrue(r_interpreted.permitted)

    def test_maximal_interpretation_cannot_exceed_lattice(self):
        """Even if the model interprets (or an attacker forces) the broadest
        possible scope, the lattice denies what no grant contains."""
        interp = self._adversarial_interpreter("req-d", json.dumps({
            "use_type": "training", "model_class": "all_models",
            "commercial": True, "attribution_required": False, "territory": ["WW"]
        }))
        maximal = interp.interpret("req-d", valid_from=T0)  # valid vocabulary — passes validation
        result = permits([make_grant()], maximal, at=T0)
        self.assertFalse(result.permitted)

    def test_recorded_poisoned_interpretation_denied_by_lattice(self):
        """The injection in the poisoned fixture produced a BROADER
        interpretation (worldwide) — which the lattice denies against the
        US+CA grant. The injection cannot expand permission."""
        poisoned_scope = self.interp.interpret(POISONED_TEXT, valid_from=T0)
        result = permits([make_grant()], poisoned_scope, at=T0)
        self.assertFalse(result.permitted)


class TestNoticeDrafterLintGate(unittest.TestCase):
    def setUp(self):
        force_offline(self)

    def test_recorded_draft_passes_lint_and_is_gemini_drafted(self):
        text, source = NoticeDrafter().draft("grant-acme-il-001", "work-repo-001", "acme-intelligence-labs")
        self.assertEqual(source, "gemini_drafted")
        self.assertTrue(RevocationLint.check_notice(text))

    def test_unavailable_falls_back_to_linted_template(self):
        text, source = NoticeDrafter().draft("grant-never-cached", "work-x", "buyer-x")
        self.assertEqual(source, "deterministic_template")
        self.assertEqual(text, TEMPLATE_NOTICE_TEXT)
        self.assertTrue(RevocationLint.check_notice(text))

    def test_overclaiming_draft_rejected_by_lint_falls_back(self):
        prompt = DRAFT_PROMPT_TEMPLATE.format(grant_id="g-bad", work_id="w-bad", counterparty_id="b-bad")
        bad_client = client_with_injected_response(
            prompt, "Your grant is terminated and your work will be removed from the model immediately."
        )
        text, source = NoticeDrafter(client=bad_client).draft("g-bad", "w-bad", "b-bad")
        self.assertEqual(source, "deterministic_template")
        self.assertEqual(text, TEMPLATE_NOTICE_TEXT)


if __name__ == "__main__":
    unittest.main()
