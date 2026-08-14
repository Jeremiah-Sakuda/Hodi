from typing import List, Optional
from datetime import datetime, timezone
from src.schema.scope import Scope, ScopeEvaluationResult
from src.schema.grant_event import GrantEvent
from src.schema.lattice import is_use_type_contained, is_model_class_contained

def permits(
    active_grants: List[GrantEvent],
    requested_scope: Scope,
    at: Optional[datetime] = None
) -> ScopeEvaluationResult:
    """
    permits(active_grants, requested_scope, at=t) — Scope Containment Resolution Engine (HOD-106).
    
    Resolves across all five gating dimensions simultaneously:
    1. Use-Type Containment (lattice partial order: training ⊃ fine_tuning ⊃ rag_retrieval ⊃ human_reference)
    2. Model-Class Containment (all_models ⊃ open_weights, proprietary_frontier)
    3. Commercial Status (commercial grant permits non-commercial request; containment is one-way)
    4. Territory Containment ('WW' covers all; an empty/absent granted territory means unrestricted
       (worldwide); a non-empty granted set without 'WW' requires the requested set to be a non-empty subset)
    5. Temporal Validity — two conditions, both required (HOD-702):
       (a) the grant is CURRENT at the evaluation instant (valid_from <= at <= valid_until), and
       (b) the REQUESTED window is CONTAINED by the grant window:
           request.valid_from >= grant.valid_from, and where the grant is bounded,
           request.valid_until <= grant.valid_until. An open-ended request
           (valid_until=None) asks for rights forever; only an unbounded grant
           contains it. Checking (a) alone was the defect: a grant valid through
           September, asked in August for rights through December, answered yes —
           the evaluation instant was inside the grant, but the requested window
           was not.
    
    # NOTE: attribution_required is deliberately NOT a gating dimension in permits().
    # Attribution is an obligation condition attached to the output license terms, not a permission gate.
    # A request that does not specify attribution against an attribution_required=True grant is PERMITTED,
    # and the returned evaluation result carries attribution_required=True.
    
    CORRECT UNION SEMANTICS: Multiple active grants resolve to the union of permitted requests.
    A request is permitted if and only if SOME SINGLE active grant contains the request across ALL
    gating dimensions simultaneously. Dimensions are NEVER merged per-dimension across grants!
    """
    eval_time = at or datetime.now(timezone.utc)

    # THE DOOR IS CLOSED, not filtered — and it is checked BEFORE any matching,
    # so a permissive answer can never be returned from a partly-invalid input.
    #
    # permits() takes the FOLDED ACTIVE state, never a raw event list. It used
    # to accept `kind in ("granted", "superseded")` and silently skip anything
    # else, which meant a caller passing raw append-only events got answers
    # computed partly from revoked and superseded history. Skipping the wrong
    # inputs quietly is how that survived; refusing them is how it stays fixed.
    #
    # Callers fold first: src/resolve/resolver.py::active_grant_events.
    for grant in active_grants:
        if grant.kind != "granted":
            raise ValueError(
                f"permits() received a '{grant.kind}' event for grant '{grant.grant_id}'. "
                "It takes the folded ACTIVE grant state, not raw append-only events — "
                "call active_grant_events(events, at=t) first (HOD-103, HOD-107)."
            )

    for grant in active_grants:
        g_scope = grant.scope

        # Dimension 5a: the grant is current at the evaluation instant.
        if eval_time < g_scope.valid_from:
            continue
        if g_scope.valid_until and eval_time > g_scope.valid_until:
            continue

        # Dimension 5b: the requested window is contained by the grant window.
        # Currency alone is not containment: it answers "is the grant alive
        # right now", not "does the grant cover what is being asked for".
        if requested_scope.valid_from < g_scope.valid_from:
            # The request asks for rights beginning before the grant did.
            continue
        if g_scope.valid_until is not None:
            if requested_scope.valid_until is None:
                # Open-ended request against a bounded grant: the grant cannot
                # contain "forever". Refuse rather than truncate — the API
                # never quietly narrows what the caller asked for.
                continue
            if requested_scope.valid_until > g_scope.valid_until:
                continue

        # Dimension 1: Use-Type Containment
        if not is_use_type_contained(g_scope.use_type, requested_scope.use_type):
            continue

        # Dimension 2: Model-Class Containment
        if not is_model_class_contained(g_scope.model_class, requested_scope.model_class):
            continue

        # Dimension 3: Commercial Status (One-way containment: commercial grant permits non-commercial request)
        if requested_scope.commercial and not g_scope.commercial:
            continue

        # Dimension 4: Territory Containment
        # An empty or absent territory list on a grant means UNRESTRICTED (worldwide),
        # equivalent to ["WW"] — never "no territories permitted". Only a non-empty
        # list without "WW" restricts.
        granted_territories = set(g_scope.territory or [])
        if granted_territories and "WW" not in granted_territories:
            requested_territories = set(requested_scope.territory or [])
            if not requested_territories:
                # An empty requested territory asks for worldwide use; a
                # territory-limited grant cannot contain it.
                continue
            if not requested_territories.issubset(granted_territories):
                continue

        # All 5 gating dimensions contained in this SINGLE active grant!
        return ScopeEvaluationResult(
            permitted=True,
            matching_grant_id=grant.grant_id,
            attribution_required=g_scope.attribution_required,
            reason=f"Request permitted by grant '{grant.grant_id}' on all 5 gating dimensions."
        )

    # No single active grant contains the requested scope on all dimensions simultaneously
    return ScopeEvaluationResult(
        permitted=False,
        matching_grant_id=None,
        attribution_required=False,
        reason="No single active grant contains the requested scope across all dimensions simultaneously."
    )
