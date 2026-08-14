"""
tests/test_signature_honesty.py — a `signature` field must not pretend to be one
(HOD-350, HOD-620).

Hodi's revocation notices, receipts and grant events carry a `signature`. None
of them are cryptographic signatures, and **nothing in the codebase verifies
one** — the values were literals (`SIG_REVOKED`, `SIG_RECEIPT`,
`SIG_REVOCATION_<grant_id>`) derived from the document's own identifiers, while
the README described "a dated signed notice" and the demo narration said "signed
notices and receipts are issued".

That is the ledger's signature failure shape applied to a legal artifact: a
stated property, a field named after the mechanism, and nothing connecting them.
The fix is not to fake a signature — HMAC with a service-held secret is
verifiable only by parties who could also forge it — but to label the value
honestly and disclose the limit. See src/schema/signing.py.

These tests fail if any runtime path emits a value that *looks* like a real
signature, or if the outward disclosure disappears.
"""

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.schema.signing import (
    PLACEHOLDER_PREFIX, SIGNATURE_CLAIM_LIMIT,
    is_unsigned_placeholder, unsigned_placeholder,
)

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIRS = [ROOT / "src", ROOT / "scripts"]

# A `signature=` keyword argument (Pydantic field) assigned a string literal.
# Deliberately lowercase-and-boundary-anchored so it matches the model field and
# NOT `HEADER_SIGNATURE = "X-Hodi-Signature"`, which names an HTTP header — a
# different concept, and one that carries a genuine HMAC.
FAKE_SIGNATURE_LITERALS = re.compile(
    r'(?<![A-Za-z_])signature\s*=\s*(?:f?["\'])(?!.*\{)(?P<value>[^"\']*)["\']')


def runtime_python_files():
    for base in RUNTIME_DIRS:
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


class PlaceholderHelperTest(unittest.TestCase):

    def test_placeholder_is_self_describing(self):
        value = unsigned_placeholder("receipt", "grant-x")
        self.assertTrue(value.startswith(PLACEHOLDER_PREFIX + ":"))
        self.assertIn("grant-x", value)
        self.assertTrue(is_unsigned_placeholder(value))

    def test_a_real_looking_value_is_not_mistaken_for_a_placeholder(self):
        for impostor in ("SIG_REVOKED", "SIG_RECEIPT", "a3f9c1e2", ""):
            self.assertFalse(is_unsigned_placeholder(impostor))


class NoHandWrittenSignatureLiteralsTest(unittest.TestCase):
    """
    The guard that actually bites: no runtime file may assign a *string literal*
    to a `signature=` field. Every value must come from unsigned_placeholder(),
    so the honest prefix cannot be bypassed by typing a new `SIG_...` constant.

    Exempted by construction: `signature=request.headers.get(...)` and other
    non-literal expressions, which this pattern does not match.
    """

    def test_no_runtime_file_assigns_a_signature_string_literal(self):
        offenders = []
        for path in runtime_python_files():
            if path.name == "signing.py":
                continue  # defines the prefix; contains no assignments
            for line_no, line in enumerate(path.read_text().splitlines(), 1):
                m = FAKE_SIGNATURE_LITERALS.search(line)
                if m is None:
                    continue
                value = m.group("value")
                # `signature=""` is the ONE permitted literal (HOD-706): the
                # pre-signing value inside a sign_pydantic(...) construction,
                # excluded from the signed payload and replaced in the returned
                # copy. Empty cannot read as a real signature; anything
                # non-empty that is not the labelled placeholder still fails.
                if value == "" or is_unsigned_placeholder(value):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "signature fields must be filled by unsigned_placeholder() or "
            "sign_pydantic() (via a temporary signature=\"\"), never a "
            "hand-written literal that reads as a real signature:\n  "
            + "\n  ".join(offenders))


class EmittedDocumentsAreLabelledTest(unittest.TestCase):
    """End-to-end: the documents a counterparty actually receives say so."""

    def setUp(self):
        import os
        os.environ["HODI_OFFLINE"] = "1"
        self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

    def test_revocation_receipt_signature_is_labelled(self):
        from src.gateway.gateway import AgentGateway
        from src.schema.revocation import RevocationNotice
        notice = RevocationNotice(
            grant_id="grant-x", counterparty_id="cp-1",
            revoked_at=datetime.now(timezone.utc), notice_text="terminated; does not un-train")
        receipt = AgentGateway().deliver_revocation_notice(
            sender="revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com",
            counterparty_id="cp-1", notice=notice)
        self.assertTrue(is_unsigned_placeholder(receipt.signature),
                        f"receipt signature is not labelled: {receipt.signature!r}")

    def test_revoked_grant_events_are_labelled(self):
        from src.agents.revocation_propagator import RevocationPropagatorAgent
        from src.gateway.gateway import AgentGateway
        from src.schema.grant_event import GrantEvent
        from src.schema.scope import Scope
        t = datetime(2026, 8, 1, tzinfo=timezone.utc)
        scope = Scope(use_type="training", model_class="all_models", commercial=True,
                      attribution_required=False, territory=[], valid_from=t, valid_until=None)
        events = [GrantEvent(event_id="e1", grant_id="g1", work_id="w1", counterparty_id="cp-1",
                             scope=scope, kind="granted", issued_at=t,
                             signature=unsigned_placeholder("grant", "g1"))]
        agent = RevocationPropagatorAgent(gateway=AgentGateway(), memory_bank_events=events)
        result = agent.execute_revocation_cascade(work_id="w1", revoked_use_type="training")
        self.assertEqual(len(result.affected_grants), 1)
        revoked = [e for e in events if e.kind == "revoked"]
        self.assertTrue(revoked, "cascade appended no revoked event to the in-memory log")
        for event in revoked:
            self.assertTrue(is_unsigned_placeholder(event.signature),
                            f"revoked event signature is not labelled: {event.signature!r}")


class DisclosureIsPublishedTest(unittest.TestCase):
    """The limit is only honest if a reader is told. If the README bullet is
    removed, this fails rather than letting the claim quietly revert."""

    def test_readme_discloses_that_signatures_are_placeholders(self):
        readme = (ROOT / "README.md").read_text()
        self.assertRegex(
            readme, r"(?i)not a cryptographic signature|signature fields are (labelled )?placeholders",
            "README must disclose that `signature` fields are placeholders")

    def test_the_claim_limit_names_the_missing_property(self):
        self.assertIn("asymmetric", SIGNATURE_CLAIM_LIMIT.lower())
        self.assertIn("verif", SIGNATURE_CLAIM_LIMIT.lower())


if __name__ == "__main__":
    unittest.main()


class CrawlerDetectorHasAPositiveControlTest(unittest.TestCase):
    """
    The detector that produces this project's headline number had never been
    asserted to FIRE. `known_crawler_ua_matches` read 0 for a week — not because
    no crawler came, but because the pattern required a word boundary before
    `bot`, so the commonest crawler-naming convention (a vendor prefix glued
    straight onto `bot`) matched nothing. A real `GPTBot` request sat in the log,
    counted as unattributed.

    A guard for a null result must include a case that makes it non-null, or the
    null is just the branch nobody exercised.

    Asserts the REGEX SET DIRECTLY — `THIRD_PARTY_BOT_USER_AGENTS` — because that
    is precisely what `scripts/daily_accrual_check.py` uses to compute the
    published figure. Going through `triage_record()` would be wrong twice: it
    calls Vertex Gemma and then Ollama before the regex, so the assertion could
    pass because a *model* said "bot" while the pattern stayed blind, and it
    would make the offline suite reach the network.
    """

    def _matches_crawler_pattern(self, user_agent: str) -> bool:
        from src.evidence.gemma_triage import GemmaTriageEngine
        return any(re.search(p, user_agent.lower())
                   for p in GemmaTriageEngine.THIRD_PARTY_BOT_USER_AGENTS)

    def test_prefix_glued_crawler_names_are_detected(self):
        """The shape that was invisible. The patterns name no vendor; these are
        only test inputs, chosen because this is the convention crawlers use."""
        for ua in ("GPTBot", "Googlebot", "Bingbot", "PetalBot", "Applebot"):
            with self.subTest(user_agent=ua):
                self.assertTrue(self._matches_crawler_pattern(ua),
                                f"{ua!r} must match a crawler signature")

    def test_conventional_crawler_forms_still_detected(self):
        for ua in ("somebot/1.0", "Mozilla/5.0 (compatible; example-bot)",
                   "BigCrawler/2.0", "a spider", "some scraper", "an indexer"):
            with self.subTest(user_agent=ua):
                self.assertTrue(self._matches_crawler_pattern(ua))

    def test_ordinary_browsers_are_not_crawlers(self):
        """The paired negative: widening the pattern must not sweep in browsers,
        or the headline number inflates instead of deflating."""
        for ua in ("Mozilla/5.0 (compatible)",
                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/135.0.0.0",
                   "curl/8.7.1", "Python-urllib/3.14"):
            with self.subTest(user_agent=ua):
                self.assertFalse(self._matches_crawler_pattern(ua))

    def test_the_published_figure_uses_this_same_pattern_set(self):
        """Guards the link between the test and the number: if the audit stops
        using THIRD_PARTY_BOT_USER_AGENTS, these assertions stop meaning
        anything about the published figure."""
        audit = (ROOT / "scripts" / "daily_accrual_check.py").read_text()
        self.assertIn("GemmaTriageEngine.THIRD_PARTY_BOT_USER_AGENTS", audit,
                      "the accrual audit no longer derives known_crawler_ua_matches "
                      "from the pattern set this test asserts")
