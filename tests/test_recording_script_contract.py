"""
tests/test_recording_script_contract.py — the recording script must remain
runnable against the API it records (HOD-730).

WHY THIS EXISTS. `docs/VIDEO-SCRIPT.md` is the one document whose failure mode
is a camera pointed at an HTTP 422. On 2026-08-14 it carried, at the very top, a
banner warning that `work_id` had become mandatory on `/api/v1/license` and
`/api/v1/license/natural` — and three of the four on-camera command bodies still
omitted it. Run against the deployed service that day, Beat 3 and the hero's
Frames A and C each returned:

    HTTP 422  {"type":"missing","loc":["body","work_id"],"msg":"Field required"}

The banner had been correct for days. Nothing checked it, so nothing fixed it.
That is the project's most-repeated defect class — a stated property, a mechanism
that does not enforce it, and nothing connecting the two — recurring in the one
document where the cost is a failed take rather than a failed test.

WHAT THIS ASSERTS. Every JSON body the script POSTs to a route is checked against
that route's Pydantic model: each required field must be present in the literal
the script tells the presenter to paste. The route table is DERIVED from
`src/api/buyer_api.py` at import time rather than transcribed here, because a
hand-copied table is the same defect wearing a different hat — add a route and
this test follows it.

WHAT IT DELIBERATELY DOES NOT ASSERT. Not whether a request is *permitted*: that
depends on live grant state and belongs to `make recording-prep`, which reports
the affected set and the predicted cascade cost before a take. This test answers
the narrower, purely-static question the 422 exposed — will the request be
accepted as well-formed at all?

The second failure that day is not statically checkable and is pinned in prose
instead: Frame A hardcoded `valid_from: "2026-08-09"` while `recording-prep`
opens the grant window at seed time, so `permits()` correctly refused a request
window not contained in the grant's, and the hero's opening frame returned
`permitted: false`. `test_license_bodies_do_not_hardcode_valid_from` catches that
specific shape.
"""

import ast
import json
import re
import unittest
from pathlib import Path

from src.api import buyer_api

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "docs" / "VIDEO-SCRIPT.md"
BUYER_API_SRC = ROOT / "src" / "api" / "buyer_api.py"

# A body the script builds through a helper rather than a literal cannot be read
# statically. None is recorded so the test reports it instead of silently
# passing — an unparsed body must never look like a checked one.
_ROUTE_CALL = re.compile(r'BASE\s*\+\s*"(/api/[^"]+)"')


def routes_to_models() -> dict:
    """Derived from the source, never transcribed: route path -> model class."""
    src = BUYER_API_SRC.read_text()
    table = {}
    for m in re.finditer(r'@router\.post\("([^"]+)".*?\)\s*\nasync def \w+\(\s*\w+\s*:\s*(\w+)',
                         src, re.S):
        model = getattr(buyer_api, m.group(2), None)
        if model is not None:
            table[m.group(1)] = model
    return table


def required_fields(model) -> set:
    return {name for name, f in model.model_fields.items() if f.is_required()}


def python_blocks(text: str) -> list:
    """Every fenced block the presenter is told to paste."""
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def literal_keys(node: ast.AST) -> set:
    """Top-level string keys of a dict literal, ignoring anything computed."""
    if not isinstance(node, ast.Dict):
        return set()
    return {k.value for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def bodies_by_route(block: str) -> list:
    """
    Pairs of (route, key-set) for each json.dumps({...}) whose result is posted.

    The script's shape is stable: a dict literal is dumped into `raw`, then a
    Request is built against BASE + "<route>". Rather than model dataflow, this
    takes every dict literal passed to json.dumps in the block and pairs it with
    every route the block posts to — the blocks are one-request-each, and pairing
    conservatively means an extra check, never a skipped one.
    """
    routes = _ROUTE_CALL.findall(block)
    if not routes:
        return []
    # Strip the heredoc wrapper so the payload parses as Python.
    body = re.sub(r"^python3 - <<'EOF'\n", "", block.strip())
    body = re.sub(r"\nEOF\s*$", "", body)
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return [(r, None) for r in routes]

    dumped = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "dumps" and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Dict):
                dumped.append(literal_keys(arg))
            elif isinstance(arg, ast.Name):
                # `raw = json.dumps(body)` — resolve the name to its assignment.
                for a in ast.walk(tree):
                    if (isinstance(a, ast.Assign) and isinstance(a.value, ast.Dict)
                            and any(isinstance(t, ast.Name) and t.id == arg.id
                                    for t in a.targets)):
                        dumped.append(literal_keys(a.value))
    return [(r, keys) for r in routes for keys in (dumped or [None])]


class RecordingScriptPostsWellFormedBodiesTest(unittest.TestCase):
    """The check that would have replaced three on-camera 422s with a red test."""

    def setUp(self):
        self.text = SCRIPT.read_text()
        self.table = routes_to_models()

    def test_route_table_was_actually_derived(self):
        """A guard reading an empty table would pass while checking nothing."""
        self.assertIn("/api/v1/license", self.table)
        self.assertIn("/api/v1/license/natural", self.table)
        self.assertIn("/api/v1/revoke", self.table)

    def test_work_id_is_required_by_both_license_routes(self):
        """
        Pins the fact the script's own banner asserted for days while three
        bodies contradicted it. If this ever goes false, the reason the test
        below exists has changed and both should be revisited together.
        """
        self.assertIn("work_id", required_fields(self.table["/api/v1/license"]))
        self.assertIn("work_id", required_fields(self.table["/api/v1/license/natural"]))

    def test_every_scripted_body_carries_every_required_field(self):
        checked = 0
        for block in python_blocks(self.text):
            for route, keys in bodies_by_route(block):
                model = self.table.get(route)
                if model is None:
                    continue
                self.assertIsNotNone(
                    keys, f"could not statically read the body posted to {route} — "
                          "rewrite it as a dict literal so this guard can check it")
                missing = required_fields(model) - keys
                checked += 1
                self.assertFalse(
                    missing,
                    f"docs/VIDEO-SCRIPT.md posts to {route} without required "
                    f"field(s) {sorted(missing)} — the deployed service answers "
                    f"HTTP 422 and the take is lost. Model: {model.__name__}")
        self.assertGreaterEqual(
            checked, 3, "the script no longer exercises the routes this guard was "
                        "written for — it is passing vacuously")

    def test_license_bodies_do_not_hardcode_valid_from(self):
        """
        `permits()` requires the REQUEST window to be contained in the GRANT
        window, and `make recording-prep` opens the grant at seed time. A
        hardcoded past `valid_from` is therefore correctly denied — which on
        2026-08-14 made the hero's opening frame return `permitted: false`.
        """
        hardcoded = re.findall(r'"valid_from"\s*:\s*"(\d{4}-\d{2}-\d{2}[^"]*)"', self.text)
        self.assertFalse(
            hardcoded,
            f"docs/VIDEO-SCRIPT.md hardcodes valid_from={hardcoded} in a request body. "
            "The grant window opens when recording-prep runs, so a fixed past date is "
            "not contained in it and the request is denied. Stamp it at call time.")


class RecordingScriptDoesNotNarrateARetiredClaimTest(unittest.TestCase):
    """
    The script told the presenter to say the `signature` field reads
    `UNSIGNED_PLACEHOLDER`. Cloud KMS signing shipped; the deployed service now
    returns `KMS-ECDSA-P256-SHA256:…`, verified on 2026-08-14. Narrating the
    placeholder would state something the screen contradicts — and would discard
    the strongest provable claim in the submission.
    """

    def setUp(self):
        self.text = SCRIPT.read_text()

    def test_no_instruction_to_narrate_the_placeholder_as_current(self):
        for m in re.finditer(r"[^\n]*UNSIGNED_PLACEHOLDER[^\n]*", self.text):
            line = m.group(0)
            # Historical explanation is fine; an instruction to say it is not.
            if re.search(r"\b(say|says|reads|shows|carries)\b", line, re.I) and \
                    "no longer" not in line.lower() and "was" not in line.lower():
                self.fail(f"VIDEO-SCRIPT.md still narrates UNSIGNED_PLACEHOLDER as current: {line!r}")


if __name__ == "__main__":
    unittest.main()
