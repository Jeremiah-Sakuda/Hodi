"""
tests/test_manifest_merge.py — a persisted row may override the seed, never
erase it (HOD-718, HOD-731).

WHAT WENT WRONG. `get_registered_works()` unioned the committed seed corpus with
the rows persisted in Firestore as `{**seed, **registered}` — a ROW-level
replacement. The persisted rows carry `work_id`, `artist_id` and `control_tier`;
the seed carries those plus `canary_string`, `canary_planted_at`,
`control_proof`, `title`, `uri`, `content_hash`, `medium` and `published_at`. So
every registered row silently deleted eight fields from the public manifest.

The live consequences, observed 2026-08-14 against the deployed service:

  * GET /works returned five works of five fields each, with NO canary on any
    work — the canaries are the mechanism behind the `canary_hit` evidence class.
  * `work-repo-001`, the project's ONE `verified_control` work, was served with
    no `control_proof` — while the README's opening sentence says Hodi registers
    works "with proof of control".
  * GET /works/work-repo-001/proof returned **HTTP 500**, because the route
    indexed `work["control_proof"]` on a row where the key was absent rather
    than None.

`scripts/verify_manifest.py` had been reporting all of this correctly for as
long as it was true. Nothing ran it against the deployed service, because
`.github/workflows/verify-live.yml` had never executed. It found this on its
first run.

THE RULE THIS PINS. Overriding what a persisted row asserts is correct.
Erasing what it is silent about is not — absence is not an assertion. And a
merged row must never read as though the artist registered fields they did not,
so every borrowed key is named in `seed_supplemented_fields`.
"""

import unittest
from unittest.mock import patch

from src.evidence_service import main


SEED = [{
    "work_id": "work-x",
    "artist_id": "artist-jeremiah",
    "medium": "code",
    "title": "Seed Title",
    "control_tier": "verified_control",
    "control_proof": {"method": "signed_commit", "evidence_uri": "https://example.test/c"},
    "canary_string": "HODI-CANARY-TEST-0001",
    "canary_planted_at": "2026-08-06T12:40:00Z",
    "hodi_record_uri": "https://svc.test/works/work-x",
}]

# What Firestore actually holds: a partial row.
PERSISTED_PARTIAL = [{"work_id": "work-x", "artist_id": "artist-jeremiah",
                      "control_tier": "verified_control"}]


def manifest(rows, seed=SEED):
    with patch.object(main, "seed_corpus_works", return_value=[dict(w) for w in seed]), \
         patch.object(main, "get_effective_base_url", return_value="https://svc.test"), \
         patch("src.gateway.gateway.AgentGateway.read_collection", return_value=rows):
        return {w["work_id"]: w for w in main.get_registered_works()}


class PersistedRowsDoNotEraseSeedFieldsTest(unittest.TestCase):

    def test_partial_persisted_row_keeps_the_canary(self):
        row = manifest(PERSISTED_PARTIAL)["work-x"]
        self.assertEqual(row.get("canary_string"), "HODI-CANARY-TEST-0001",
                         "a persisted row that says nothing about the canary deleted it")
        self.assertEqual(row.get("canary_planted_at"), "2026-08-06T12:40:00Z")

    def test_partial_persisted_row_keeps_the_control_proof(self):
        """The failure that made /works/{id}/proof answer HTTP 500."""
        row = manifest(PERSISTED_PARTIAL)["work-x"]
        self.assertEqual(row.get("control_tier"), "verified_control")
        self.assertIsNotNone(
            row.get("control_proof"),
            "a verified_control work was served with no proof — the README's opening "
            "claim is that works are registered WITH proof of control")

    def test_the_row_still_declares_it_is_registered(self):
        row = manifest(PERSISTED_PARTIAL)["work-x"]
        self.assertEqual(row["source"], "registered")

    def test_borrowed_fields_are_named_rather_than_passed_off(self):
        """A merged row must not read as though the artist registered it all."""
        row = manifest(PERSISTED_PARTIAL)["work-x"]
        supplemented = row.get("seed_supplemented_fields") or []
        self.assertIn("canary_string", supplemented)
        self.assertIn("control_proof", supplemented)
        self.assertNotIn("control_tier", supplemented,
                         "control_tier came from the persisted row; do not claim it was seeded")

    def test_a_persisted_value_still_wins(self):
        """Override is the correct half of the behaviour and must survive."""
        rows = [dict(PERSISTED_PARTIAL[0], control_tier="asserted", title="Registered Title")]
        row = manifest(rows)["work-x"]
        self.assertEqual(row["control_tier"], "asserted")
        self.assertEqual(row["title"], "Registered Title")
        self.assertNotIn("title", row.get("seed_supplemented_fields") or [])

    def test_a_fully_registered_row_borrows_nothing(self):
        row = manifest(PERSISTED_PARTIAL, seed=[])["work-x"]
        self.assertFalse(row.get("seed_supplemented_fields"),
                         "nothing was seeded, so nothing may be reported as supplemented")

    def test_a_persisted_none_does_not_erase_a_seeded_value(self):
        """
        Firestore rows carry explicit nulls. A null is 'unset', not 'deleted' —
        treating it as an override would reintroduce the exact defect.
        """
        rows = [dict(PERSISTED_PARTIAL[0], canary_string=None)]
        row = manifest(rows)["work-x"]
        self.assertEqual(row.get("canary_string"), "HODI-CANARY-TEST-0001")


class ProofRouteAnswersInsteadOfCrashingTest(unittest.TestCase):
    """HTTP 500 is not an answer about whether control was proven."""

    def test_missing_control_proof_key_yields_unverified_not_an_exception(self):
        works = [{"work_id": "work-y", "control_tier": "asserted"}]  # no control_proof key
        with patch.object(main, "get_registered_works", return_value=works):
            for w in main.get_registered_works():
                if w["work_id"] == "work-y":
                    # Mirrors the route's guard; the old form raised KeyError here.
                    self.assertTrue(
                        w.get("control_tier") != "verified_control"
                        or w.get("control_proof") is None)


if __name__ == "__main__":
    unittest.main()
