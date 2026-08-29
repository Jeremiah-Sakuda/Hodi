"""
Class-A structural guard: every mutating route must authenticate (HOD-311, HOD-360).

Three defect classes recurred after being fixed once. This one — identity taken
from attacker-controlled input, or not taken at all — recurred as a LIVE
SECURITY HOLE both times:

  2026-08-07  /api/v1/license      read another counterparty's grants, anonymously
  2026-08-08  /api/v1/revoke       revoked any published work_id, anonymously

The second was three lines below the first handler in the same file. Fixing the
reported route instead of asserting the property across all routes is what
allowed it. Nothing in CI would have caught either.

This test enumerates the router's own routes and fails if any mutating method
reaches an endpoint that does not authenticate. A new unauthenticated POST
cannot be merged without either wiring the authenticator or consciously adding
the path to PUBLIC_ROUTES below, in the diff, where a reviewer sees it.
"""

import inspect
import os
import re
import typing
import unittest
from unittest import mock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.api.buyer_api import router  # noqa: F401 - kept for the router/app parity check
from src.evidence_service.main import app

# GET is in this set, and that is the point.
#
# It used to be {POST, PUT, PATCH, DELETE}, on the assumption that HTTP method
# tells you whether a handler writes. It does not. `/internal/accrual_audit` is
# a GET that APPENDS audit rows, and it was therefore never enumerated by the
# guard whose whole job is to enumerate the routes that write. An external
# reviewer added an anonymous GET that ran the full revocation cascade and every
# CI target stayed green.
#
# So the guard now covers every route on the app and requires each one to be
# either authenticated or named in PUBLIC_ROUTES with a reason. Method is a hint
# about intent, never evidence about behaviour.
MUTATING_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Retained ONLY as a diagnostic in failure messages. It is no longer what the
# guard asserts.
#
# It was a substring search over the endpoint's source, which means a handler
# whose entire authentication was the comment
#
#     # TODO: wire _authenticate_or_403()
#
# passed the check. `_domain_service_or_404` was in this list and authenticates
# nobody — it maps an unknown domain name to a 404. A test that reads source
# text cannot distinguish code from a note about code; the replacement calls the
# route and looks at what comes back.
AUTH_MARKER_HINTS = ("_authenticate_or_403", "verify_scheduler_oidc", "verify_front_door_oidc")

# Framework-generated documentation routes. Not application surface.
FRAMEWORK_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

# Deliberately public routes, each with the reason it is safe.
# Adding to this set is a visible, reviewable act.
PUBLIC_ROUTES = {
    # --- public by design: the crawler-facing consent surface -------------
    # These exist to be fetched anonymously by anything that crawls. A
    # consent signal nobody can read without credentials signals nothing.
    "/robots.txt",
    "/sitemap.xml",
    "/.well-known/hodi.json",
    "/",
    # Registered works and canary listings are the public record of what is
    # claimed. Publishing them is the point; they carry no counterparty data.
    "/works",
    "/canaries",
    # Aggregate counts only — no per-counterparty rows. Verified by
    # test_evidence_counts_are_aggregate_only.
    "/evidence-counts",
    # The PUBLIC half of an asymmetric keypair. Anyone must be able to fetch
    # it; that is what makes a signature independently verifiable.
    "/verification-key",
    # Per-work views of the same public manifest as /works, and the stored
    # control proof for one work. Read-only, no counterparty data, and the
    # proof is exactly the artifact a third party needs in order to check an
    # ownership claim without asking anyone's permission.
    "/works/{work_id}",
    "/works/{work_id}/proof",
    # Reads only, under a hardcoded session context, against policy-permitted
    # collections; structurally cannot return another counterparty's data and
    # writes nothing. Exists so a reviewer can verify the boundary without
    # credentials.
    "/api/v1/debug/compromised_agent_read",
    # --- the public /demo sandbox (HOD-760) --------------------------------
    # Unauthenticated BY DESIGN: this is the interactive walkthrough anyone can
    # try. Its safety is not a credential — it is policy data. Every route runs
    # as `sandbox_agent`, which the gateway denies every real collection, proven
    # in tests/test_demo_sandbox_boundary.py. Listing them here is the visible,
    # reviewed act the guard exists to force.
    "/demo",                        # the page itself — a public GET
    "/demo/api/session",            # mints an isolated sandbox; rate-limited per IP
    "/demo/api/{sid}/license",      # pure permits() over the sandbox grant; no writes
    "/demo/api/{sid}/revoke",       # real cascade over demo_* only; sandbox role; signature-capped
    "/demo/api/fleet-drill",        # real ADK fleet delegation, write-free (reads fixtures, appends nothing)
    "/demo/api/interpret",          # real Gemini scope interpreter (cache-backed), read-only
    # --- the platform sandbox (HOD-780): Studio + Market journeys -----------
    # Same boundary as the guided demo: every call crosses the gateway as
    # `sandbox_agent`, denied at every real collection. Registration stores a
    # claim (title, medium, sha256) — never file content; the live interpreter
    # call is text-length-, session- and IP-capped.
    "/demo/api/{sid}/works",           # GET: seeded + registered works · POST: register a claim, demo_works only
    "/demo/api/{sid}/request-license", # live Gemini interpret + deterministic decision; grant appends to demo_grants only
    "/demo/api/{sid}/grants",          # read-only ledger over demo_* collections
}


def _walk(routes, prefix=""):
    """
    Every route reachable on the app, recursing into included routers.

    THIS RECURSION IS THE WHOLE FIX, AND IT IS NOT COSMETIC. On this FastAPI
    version `app.include_router(...)` does NOT flatten the router's routes into
    `app.routes` — it stores a single `_IncludedRouter` entry holding them. A
    naive iteration over `app.routes` therefore yields the deployed module's own
    routes and NONE of the buyer API's, while `TestClient` happily serves both.
    A guard written that way would have reported success over an enumeration
    missing every route that has ever actually broken in this project.
    """
    for route in routes:
        # An included router is reached through `original_router` on this
        # FastAPI version; `route.routes` on the wrapper is a plain string, so
        # a duck-typed `getattr(route, "routes")` walk silently finds nothing.
        inner = getattr(route, "original_router", None)
        sub = getattr(inner, "routes", None) if inner is not None else None
        if sub is None:
            candidate = getattr(route, "routes", None)
            sub = candidate if isinstance(candidate, (list, tuple)) else None
        if sub:
            yield from _walk(sub, prefix)
            continue
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if path is None or endpoint is None:
            continue
        yield prefix + path, getattr(route, "methods", set()) or set(), endpoint


def mutating_routes():
    """
    Every mutating route on the APPLICATION THE DOCKERFILE SERVES.

    THE HOLE THIS CLOSES. This enumerated `buyer_api.router` alone. An external
    reviewer added an unauthenticated mutating POST directly to
    `src/evidence_service/main.py` — the module Cloud Run actually runs — and
    ALL SIX CI TARGETS PASSED, including this one. The README cites this guard
    as the reason two historical auth holes "would have been caught on first
    commit"; it could not have caught them on the module that serves them.

    Four such routes already existed when the hole was found — the three
    `/internal/domain/*` operations and `/internal/revocation/execute` — all of
    them authenticated, so nothing was exposed. The guard simply could not have
    known either way.
    """
    seen = set()
    for path, methods, endpoint in _walk(app.routes):
        mutating = methods & MUTATING_METHODS
        if not mutating:
            continue
        key = (path, tuple(sorted(mutating)))
        if key in seen:
            continue
        seen.add(key)
        yield path, sorted(mutating), endpoint


_DUMMY = {
    str: "probe", int: 1, float: 1.0, bool: True,
    dict: {}, list: [],
}


def _sample(annotation):
    """A minimal value satisfying `annotation`, for a request body the route
    will actually parse."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Literal:
        return args[0]
    if origin in (list, typing.List):
        return [_sample(args[0])] if args else []
    if origin in (dict, typing.Dict):
        return {}
    if origin is typing.Union:  # includes Optional
        non_none = [a for a in args if a is not type(None)]
        return _sample(non_none[0]) if non_none else None
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return _sample_model(annotation)
        if annotation is datetime:
            return datetime.now(timezone.utc).isoformat()
        for base, value in _DUMMY.items():
            if issubclass(annotation, base):
                return value
    return "probe"


def _pattern_sample(pattern):
    """A string satisfying a simple anchored character-class pattern.

    Handles `^[class]{n}$`, `^[class]{n,m}$`, `^[class]+$` and `^[class]*$` —
    the shapes this codebase uses (`^[a-f0-9]{64}$` for content hashes,
    `^[A-Za-z0-9_.:-]+$` for identifiers). Anything else RAISES rather than
    returning a value the route will reject: a probe body that 422s never
    reaches the authenticator, and a guard that shrugged at that would assert
    nothing while looking green. The failure names the pattern so the fix is a
    one-line addition here, in the diff.
    """
    match = re.fullmatch(r"\^\[([^\]]+)\]([+*]|\{(\d+)(?:,\d*)?\})\$", pattern)
    if not match:
        raise AssertionError(
            f"no sample known for pattern {pattern!r}; teach _pattern_sample this "
            "shape or add the field to FIELD_OVERRIDES, so the probe still reaches "
            "the authenticator")
    charset, quant, count = match.group(1), match.group(2), match.group(3)
    length = int(count) if count else 1

    # Expand the class enough to pick a character that is certainly a member.
    expanded = re.sub(r"(\w)-(\w)", lambda m: "".join(
        chr(c) for c in range(ord(m.group(1)), ord(m.group(2)) + 1)), charset)
    candidates = [c for c in "a0Az" if c in expanded] or [c for c in expanded if c.isalnum()]
    if not candidates:
        raise AssertionError(f"no alphanumeric member of character class {charset!r}")
    return candidates[0] * length


# Explicit values for fields whose constraint is not a simple character class.
# Listed rather than guessed, so a probe that stops being valid is a visible
# edit and not a silent 422.
FIELD_OVERRIDES = {
    "published_at": "2026-01-01",
}


def _sample_model(model):
    """Fill every REQUIRED field of a Pydantic model with a dummy value.

    Needed because FastAPI validates the body before the handler runs, so an
    empty body returns 422 and the authenticator is never reached. A guard that
    accepted 422 as "refused" would be satisfied by a route that rejects
    malformed input and authorizes anything well-formed — which is the opposite
    of the property being asserted.
    """
    body = {}
    for name, field in model.model_fields.items():
        if not field.is_required():
            continue
        key = field.alias or name
        if name in FIELD_OVERRIDES:
            body[key] = FIELD_OVERRIDES[name]
            continue
        def constraint(attr):
            return next((getattr(m, attr) for m in field.metadata
                         if getattr(m, attr, None) is not None), None)

        pattern = constraint("pattern")
        value = _pattern_sample(pattern) if pattern else _sample(field.annotation)

        # Honour length constraints too. `work_id` is min_length=3, and a
        # one-character sample 422s — which the effect test correctly reports as
        # a broken probe rather than a passing route.
        minimum = constraint("min_length")
        if isinstance(value, str) and minimum and len(value) < minimum:
            value = (value * minimum)[:minimum]
        maximum = constraint("max_length")
        if isinstance(value, str) and maximum and len(value) > maximum:
            value = value[:maximum]
        body[key] = value
    return body


def _probe_body(endpoint):
    """The request body for an unauthenticated probe of `endpoint`."""
    for param in inspect.signature(endpoint).parameters.values():
        annotation = param.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return _sample_model(annotation)
    return {}


REFUSAL_CODES = {401, 403}

# Parameterised routes were SKIPPED, not probed: the loop carried
# `or "{" in path: continue`. An anonymous POST /api/v1/pwn/{victim} running the
# full revocation cascade therefore passed every CI target, while the identical
# route without a path parameter was caught — the exemption was the whole
# difference. A guard narrated in Beat 5 as "CI fails if any mutating route
# forgets to authenticate" was blind to an entire path shape.
#
# Path parameters are filled with a benign literal instead. The value never
# needs to identify a real resource: authentication is checked before the
# resource is looked up, and if a route were to 404 on the placeholder first,
# that is itself reported below rather than counted as a refusal.
_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _concrete(path: str) -> str:
    return _PATH_PARAM.sub("probe", path)

# The four /internal/* routes call _domain_service_or_404 BEFORE authenticating,
# so with HODI_SERVICE_ROLE unset they return 404 to everyone and the
# authenticator underneath is never exercised. Probing them in that state would
# record "not reachable" as though it were "refused" — the guard would pass on a
# route it never actually tested. The probe sets the role so the real path runs.
PROBE_ENV = {"HODI_SERVICE_ROLE": "rights_custodian"}


def _probe(client, method, path, body):
    """One unauthenticated request, with the domain-service role established."""
    with mock.patch.dict(os.environ, PROBE_ENV):
        return client.request(method, path, json=body)


class TestEveryMutatingRouteAuthenticates(unittest.TestCase):
    def test_the_app_actually_exposes_mutating_routes(self):
        """Guard the guard: if this returns nothing, the check below is vacuous."""
        self.assertGreaterEqual(len(list(mutating_routes())), 3)

    def test_the_app_covers_strictly_more_than_the_router(self):
        """
        The regression that mattered. If this ever reports equality again,
        someone has narrowed the enumeration back to the router and the
        deployed module's own routes are unguarded once more.
        """
        app_paths = {p for p, _, _ in mutating_routes()}
        router_paths = {r.path for r in router.routes
                        if getattr(r, "methods", set()) & MUTATING_METHODS}
        self.assertTrue(router_paths <= app_paths,
                        "the app enumeration lost routes the router exposes")
        self.assertGreater(
            len(app_paths - router_paths), 0,
            "the deployed app exposes no mutating route outside the buyer router. If that is "
            "genuinely true now, this guard has stopped covering the module that broke.")

    def test_every_route_refuses_an_unauthenticated_call_or_is_explicitly_public(self):
        """THE EFFECT TEST. Calls each route with no credentials and requires a
        refusal.

        This replaced a substring search for `_authenticate_or_403` in the
        endpoint's source. That search could not tell code from a comment about
        code: a handler whose only authentication was

            # TODO: wire _authenticate_or_403()

        satisfied it, and `_domain_service_or_404` — which authenticates nobody —
        was listed as an auth marker. An anonymous GET running the full
        revocation cascade passed every CI target.

        The probe sends a VALID body, because FastAPI validates before the
        handler runs; accepting 422 as a refusal would mean accepting "rejects
        malformed input" as evidence of "requires credentials".
        """
        client = TestClient(app, raise_server_exceptions=False)
        failures = []
        for path, methods, endpoint in mutating_routes():
            if path in PUBLIC_ROUTES or path in FRAMEWORK_ROUTES:
                continue
            body = _probe_body(endpoint)
            for method in methods:
                response = _probe(client, method, _concrete(path), body)
                if response.status_code in REFUSAL_CODES:
                    continue
                if response.status_code == 422:
                    failures.append(
                        f"{method} {path} -> {endpoint.__name__}() rejected the probe body "
                        "as malformed (HTTP 422), so the authenticator was never reached. "
                        "This is a BROKEN PROBE, not a passing route: fix the sample body "
                        f"(_sample_model / FIELD_OVERRIDES). Detail: {str(response.json())[:200]}")
                    continue
                source = inspect.getsource(endpoint)
                hint = ("no authenticator appears in its source"
                        if not any(m in source for m in AUTH_MARKER_HINTS)
                        else "an authenticator appears in its source but did not refuse")
                failures.append(
                    f"{method} {path} -> {endpoint.__name__}() returned "
                    f"HTTP {response.status_code} to an unauthenticated caller ({hint})")

        self.assertEqual(
            failures, [],
            "Route(s) served an unauthenticated caller:\n  " + "\n  ".join(failures)
            + "\n\nEither authenticate, or add the path to PUBLIC_ROUTES with the "
              "reason it is safe.")

    def test_the_effect_probe_reaches_past_body_validation(self):
        """Guard the guard. If the synthesized body stopped satisfying the
        route's model, every probe would 422, no probe would return a refusal
        code, and the test above would fail loudly rather than pass vacuously —
        but only if a refusal is genuinely observed somewhere. This asserts that
        at least one route was actually driven to a 401/403."""
        client = TestClient(app, raise_server_exceptions=False)
        refusals = 0
        for path, methods, endpoint in mutating_routes():
            if path in PUBLIC_ROUTES or path in FRAMEWORK_ROUTES:
                continue
            for method in methods:
                r = _probe(client, method, _concrete(path), _probe_body(endpoint))
                if r.status_code in REFUSAL_CODES:
                    refusals += 1
        self.assertGreaterEqual(
            refusals, 5,
            "fewer than five routes refused an anonymous call — the probe is "
            "probably being rejected as malformed before it reaches any authenticator")

    def test_known_sensitive_routes_are_covered_by_name(self):
        """Belt and braces: the two routes that actually broke are named here, so
        a refactor that renames or drops them fails loudly rather than silently
        removing their coverage."""
        paths = {path for path, _, _ in mutating_routes()}
        for required in ("/api/v1/license", "/api/v1/license/natural", "/api/v1/revoke"):
            self.assertIn(required, paths)

    def test_revoke_requires_the_artist_principal_specifically(self):
        """/api/v1/revoke authenticating is necessary but not sufficient — a
        buyer credential must not be able to terminate an artist's grants."""
        endpoint = next(e for p, _, e in mutating_routes() if p == "/api/v1/revoke")
        source = inspect.getsource(endpoint)
        self.assertIn('required_principal_type="artist"', source)

    def test_public_exemptions_are_justified_in_the_source(self):
        """An exemption without a written reason is how this list rots."""
        source = inspect.getsource(inspect.getmodule(self.__class__))
        for path in PUBLIC_ROUTES:
            self.assertIn(path, source)


if __name__ == "__main__":
    unittest.main()
