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
the path to PUBLIC_MUTATING_ROUTES below, in the diff, where a reviewer sees it.
"""

import inspect
import unittest

from src.api.buyer_api import router

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# The authenticator (or a name that provably delegates to it) must appear in the
# endpoint's source. Kept as names rather than call-graph analysis so the check
# stays obvious and cheap.
AUTH_MARKERS = ("_authenticate_or_403", "verify_scheduler_oidc")

# Deliberately public mutating routes, each with the reason it is safe.
# Adding to this set is a visible, reviewable act.
PUBLIC_MUTATING_ROUTES = {
    # Reads only, under a hardcoded session context, against policy-permitted
    # collections; structurally cannot return another counterparty's data and
    # writes nothing. Exists so a reviewer can verify the boundary without
    # credentials.
    "/api/v1/debug/compromised_agent_read",
}


def mutating_routes():
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        if methods & MUTATING_METHODS:
            yield route.path, sorted(methods & MUTATING_METHODS), route.endpoint


class TestEveryMutatingRouteAuthenticates(unittest.TestCase):
    def test_the_router_actually_exposes_mutating_routes(self):
        """Guard the guard: if this returns nothing, the check below is vacuous."""
        self.assertGreaterEqual(len(list(mutating_routes())), 3)

    def test_every_mutating_route_authenticates_or_is_explicitly_public(self):
        unauthenticated = []
        for path, methods, endpoint in mutating_routes():
            if path in PUBLIC_MUTATING_ROUTES:
                continue
            source = inspect.getsource(endpoint)
            if not any(marker in source for marker in AUTH_MARKERS):
                unauthenticated.append(f"{','.join(methods)} {path} -> {endpoint.__name__}()")

        self.assertEqual(
            unauthenticated, [],
            "Mutating route(s) reach an endpoint that never authenticates:\n  "
            + "\n  ".join(unauthenticated)
            + "\n\nEither call _authenticate_or_403(), or add the path to "
              "PUBLIC_MUTATING_ROUTES with the reason it is safe.",
        )

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
        for path in PUBLIC_MUTATING_ROUTES:
            self.assertIn(path, source)


if __name__ == "__main__":
    unittest.main()
