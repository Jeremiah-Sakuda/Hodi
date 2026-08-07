"""
src/llm/notice_drafter.py — Gemini-drafted revocation notices, gated by the
deterministic RevocationLint (HOD-301, HOD-350).

Generation gated by an honesty check: every drafted notice passes
RevocationLint.check_notice() before it is used. If Gemini is unavailable or
the draft fails the lint, the deterministic template is used instead — and the
template is ALSO linted, so no code path emits an unlinted notice.
"""

from typing import Optional

from src.evidence.revocation_lint import RevocationLint, RevocationLintError
from src.llm.vertex_gemini import VertexGeminiClient, GeminiUnavailableError, PINNED_INTERPRETER_MODEL

# The deterministic fallback — the exact text the propagator shipped before drafting existed.
TEMPLATE_NOTICE_TEXT = (
    "This grant is hereby terminated. Please note that this revocation "
    "terminates the legal license but does not un-train the model."
)

DRAFT_PROMPT_TEMPLATE = """Draft a two-to-three sentence formal revocation notice for a content-license grant.

Facts:
- Grant ID: {grant_id}
- Work ID: {work_id}
- Counterparty: {counterparty_id}

Hard requirements:
1. State explicitly that the grant is terminated (use the word "terminated" or "revoked").
2. State explicitly that this revocation does not un-train any model (use the exact phrase "does not un-train").
3. Make NO claim that anything will be removed, erased, forgotten, or unlearned from any model.
4. Output only the notice text, no headings or salutations.
"""


class NoticeDrafter:
    def __init__(self, client: Optional[VertexGeminiClient] = None):
        self.client = client or VertexGeminiClient()
        self.model_id = PINNED_INTERPRETER_MODEL

    def draft(self, grant_id: str, work_id: str, counterparty_id: str) -> tuple[str, str]:
        """Returns (notice_text, source) where source is 'gemini_drafted' or
        'deterministic_template'. The returned text has ALWAYS passed the lint."""
        prompt = DRAFT_PROMPT_TEMPLATE.format(
            grant_id=grant_id, work_id=work_id, counterparty_id=counterparty_id
        )
        try:
            drafted = self.client.generate(prompt, model_id=self.model_id).strip()
            RevocationLint.check_notice(drafted)
            return drafted, "gemini_drafted"
        except (GeminiUnavailableError, RevocationLintError):
            RevocationLint.check_notice(TEMPLATE_NOTICE_TEXT)
            return TEMPLATE_NOTICE_TEXT, "deterministic_template"
