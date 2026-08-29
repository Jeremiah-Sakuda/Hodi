"""
tests/test_recording_script_contract.py — the recording script must remain
runnable against the surface it records (HOD-730, rewritten for HOD-780).

WHY THIS EXISTS. `docs/VIDEO-SCRIPT.md` is the one document whose failure mode
is a camera pointed at something that is not there. The first version of this
guard existed because the terminal-era script POSTed literal curl bodies and
three of them omitted a newly mandatory field — Beat 3 returned HTTP 422 on
camera. The script is now a browser walkthrough: the presenter never types a
request, so the statically checkable contract moved. What can now fail on
camera is the script directing a CLICK on a control, or citing an on-screen
label, that the demo page does not actually render.

WHAT THIS ASSERTS, derived from the artifacts rather than transcribed:
  * every control the script tells the presenter to press exists, verbatim, in
    `src/demo/index.html` — a renamed button breaks the take, so it breaks CI;
  * every on-screen label the pre-flight tells the presenter to verify exists
    on the page;
  * the stated word count is the real one, and the arithmetic fits the 4:00
    cap at a normal speaking pace;
  * the Google Cloud proof (the `.run.app` URL, said aloud) is in step 1 and
    named in the never-cut list — the panel's actual finding, pinned so an
    edit cannot quietly undo it.

WHAT IT DELIBERATELY DOES NOT ASSERT. Not what the live service will return —
that is the point of the demo being live, and the numbers rule in the script
already directs the presenter to read the screen, not the page.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "docs" / "VIDEO-SCRIPT.md"
DEMO_PAGE = ROOT / "src" / "demo" / "index.html"

FOUR_MINUTE_CAP_SECONDS = 240
SPEAKING_WPM = 145  # the pace the terminal-era guard already used


def _script() -> str:
    return SCRIPT.read_text()


def _page() -> str:
    return DEMO_PAGE.read_text()


class ScriptedClicksExistOnThePageTest(unittest.TestCase):
    """A directed click on a control the page does not render is the browser
    era's HTTP 422 — same defect, different surface."""

    # Extracted from the script's **Do:**/click directions at test time, so a
    # reworded script keeps being checked rather than silently unchecked.
    CLICK_LINE = re.compile(r"\*\*(?:①|②|③|④)?\s*([A-Z][^*]+?)\*\*(?:\s*\(|\s*—|\s*·|:)|click \*\*([^*]+?)\*\*")

    def _directed_controls(self):
        text = _script()
        controls = set()
        for m in re.finditer(r"click \*\*([^*]+?)\*\*", text):
            controls.add(m.group(1).strip().rstrip("→").strip())
        # the four inline step-4 buttons are directed as ①–④ bold headings
        for m in re.finditer(r"\*\*[①②③④]\s*([^*]+?)\*\*", text):
            controls.add(m.group(1).split("(")[0].split("—")[0].strip())
        return {c for c in controls if c and c.lower() not in {"do", "stamp"}}

    def test_the_guard_is_not_vacuous(self):
        controls = self._directed_controls()
        self.assertGreaterEqual(
            len(controls), 4,
            f"almost no directed clicks parsed from the script ({controls}) — "
            "if the direction style was reworded, update the extraction, do not delete the check")

    def test_every_directed_control_renders_on_the_demo_page(self):
        page = _page().lower()
        missing = []
        for control in self._directed_controls():
            # match case-insensitively and tolerate markup between words
            needle = control.lower().replace("’", "'")
            if needle not in page.replace("’", "'"):
                missing.append(control)
        self.assertEqual(
            missing, [],
            f"the script directs clicks on controls the demo page does not render: {missing}. "
            "Rename the script direction or the page control — on camera this is a dead click.")

    def test_stamp_control_exists(self):
        """The hero click is directed as **Stamp** with a longer on-page label;
        asserted separately because the substring rule above exempts it."""
        self.assertIn("Stamp · take it back", _page())


class CitedOnScreenLabelsExistTest(unittest.TestCase):
    """The pre-flight tells the presenter to verify three things are legible.
    Each must actually be rendered by the page (or provably fetched into it)."""

    def test_model_and_surface_labels_exist(self):
        page = _page()
        self.assertIn("Vertex AI", page)
        self.assertIn("Cloud Trace", page)
        # the model id arrives from /demo/api/interpret and is rendered into
        # #drawn; the page must carry that wiring
        self.assertIn("interpreter_model", page)

    def test_the_audit_figures_are_fetched_not_frozen(self):
        """The regression this rewrite exists for: the crawler count was an
        HTML literal (17) and the audit moved. The page must fetch the
        committed audit and must not carry a literal count near the label."""
        page = _page()
        self.assertIn("/metrics-snapshot", page)
        stat_zone = page[page.find("crawlN") - 400: page.find("crawlN") + 400]
        self.assertNotRegex(
            stat_zone, r">\s*\d+\s*<",
            "a literal number is rendered where the crawler count belongs — "
            "figures on this panel must come from /metrics-snapshot")


class ScriptTimingIsArithmeticNotAspirationTest(unittest.TestCase):
    """The 4-minute cap is a contest rule; the claim '~480 spoken words ·
    lands ≈3:45' must be arithmetic over the actual narration."""

    def _spoken_words(self) -> int:
        text = _script()
        words = 0
        for block in re.findall(r"^> (.+)$", text, re.M):
            words += len(re.findall(r"[\w’'-]+", block))
        return words

    def test_narration_parsed(self):
        self.assertGreater(self._spoken_words(), 300,
                           "almost no narration blocks parsed — the '>' quoting "
                           "convention changed; update the parser, do not delete the check")

    def test_stated_word_count_is_the_real_one(self):
        stated = re.search(r"~(\d+) spoken words", _script())
        self.assertIsNotNone(stated, "the script no longer states its word count")
        actual = self._spoken_words()
        self.assertLessEqual(
            abs(int(stated.group(1)) - actual), 40,
            f"the script says ~{stated.group(1)} words but carries {actual} — "
            "restate the count; a budget that is not re-derived is aspiration")

    def test_narration_fits_the_cap_with_room_for_the_live_actions(self):
        speech_seconds = self._spoken_words() / SPEAKING_WPM * 60
        self.assertLess(
            speech_seconds, FOUR_MINUTE_CAP_SECONDS - 45,
            f"narration alone is {speech_seconds:.0f}s at {SPEAKING_WPM} wpm; the live "
            "cascade, fleet run, attacks, and pauses need at least 45s of the cap")

    def test_step_timestamps_are_monotonic_and_inside_the_cap(self):
        marks = [int(m.group(1)) * 60 + int(m.group(2))
                 for m in re.finditer(r"~?(\d):(\d\d)–(\d):(\d\d)", _script())]
        self.assertGreaterEqual(len(marks), 4, "step time ranges no longer parse")
        ends = [int(m.group(3)) * 60 + int(m.group(4))
                for m in re.finditer(r"~?(\d):(\d\d)–(\d):(\d\d)", _script())]
        self.assertEqual(marks, sorted(marks), "step start times are not monotonic")
        self.assertLessEqual(max(ends), FOUR_MINUTE_CAP_SECONDS,
                             "a step's stated end exceeds the 4:00 cap")


class GoogleCloudProofIsEarlyAndUncuttableTest(unittest.TestCase):
    """The panel's actual finding, pinned: the deployment proof must land in
    step 1 and be excluded from the cut ladder."""

    def test_run_app_proof_is_in_step_one(self):
        text = _script()
        step1 = text[text.find("## 1 ·"): text.find("## 2 ·")]
        self.assertIn("Cloud Run", step1)
        self.assertIn("address in the top bar", step1)

    def test_the_url_line_is_in_the_never_cut_list(self):
        text = _script()
        never = re.search(r"\*\*Never cut:\*\*((?:.|\n)+?)(?=\n- |\n\n)", text)
        self.assertIsNotNone(never, "the script lost its never-cut list")
        self.assertIn("Cloud Run URL", never.group(1))

    def test_the_cut_ladder_does_not_contain_the_proof(self):
        text = _script()
        ladder = re.search(r"cut in this order:\*\*(.+)", text)
        self.assertIsNotNone(ladder, "the script lost its cut ladder")
        self.assertNotIn("Cloud Run", ladder.group(1))


if __name__ == "__main__":
    unittest.main()
