"""
src/schema/negotiation.py — the artist policy and negotiation types (HOD-713).

Licensing need not be binary. A buyer agent may PROPOSE, and Hodi may
COUNTEROFFER — but the counteroffer is the proposal CLAMPED to the artist's
per-work policy, computed deterministically. Gemini may phrase the exchange;
it cannot move the clamp. That is the same thesis as the licensing path —
the model interprets intent, the lattice decides — applied to negotiation:
no proposal, cooperative or adversarial, and no economic sweetener, yields
an agreed scope outside the policy.

Scope terms ONLY. There is no price, no escrow, no marketplace here — the
no-payments non-goal stands. A buyer may name a number in prose; the
deterministic core neither stores it nor lets it widen scope.
"""

from typing import List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from src.schema.scope import Scope, UseType, ModelClass
from src.schema.lattice import is_use_type_contained


class ArtistPolicy(BaseModel):
    """
    The artist's standing negotiation boundary for ONE work: the MOST a buyer
    can be granted, per dimension. A proposal is clamped to this; it is never
    the floor, always the ceiling.
    """
    work_id: str
    max_use_type: UseType                       # the highest use-type on offer
    allowed_model_class: ModelClass = "all_models"
    commercial_allowed: bool = False
    territory_allowed: List[str] = Field(default_factory=lambda: ["WW"])
    max_duration_days: Optional[int] = None     # None = unbounded duration allowed
    attribution_always_required: bool = False
    prohibited_use_types: List[UseType] = Field(default_factory=list)


class NegotiationProposal(BaseModel):
    counterparty_id: str
    work_id: str
    requested_scope: Scope
    # Prose only; the deterministic core ignores it for scope purposes. It
    # exists so a model-drafted exchange has somewhere to put "we'll pay $1M",
    # and so a test can PROVE the number changed nothing.
    economic_note: Optional[str] = None


NegotiationStatus = Literal["AGREED", "COUNTEROFFER", "COUNTEROFFER_REJECTED_BY_POLICY"]


class NegotiationOutcome(BaseModel):
    status: NegotiationStatus
    work_id: str
    counterparty_id: str
    # The scope Hodi is willing to grant — the proposal ∩ policy. Present on
    # AGREED and COUNTEROFFER; None when even the floor is prohibited.
    offered_scope: Optional[Scope] = None
    # Every dimension the clamp moved, in plain terms, so the exchange is
    # explainable without a diff.
    clamped_dimensions: List[str] = Field(default_factory=list)
    rationale: str


def clamp_to_policy(proposal: NegotiationProposal, policy: ArtistPolicy) -> NegotiationOutcome:
    """
    The deterministic heart of HOD-713. Returns AGREED if the proposal already
    sits inside the policy on every dimension, COUNTEROFFER with the clamped
    scope if it can be narrowed to fit, and COUNTEROFFER_REJECTED_BY_POLICY if
    the requested use is prohibited outright (no narrowing can rescue it).

    A model may render any of these outcomes into prose; it may not produce a
    fourth, and it may not widen `offered_scope`.
    """
    req = proposal.requested_scope
    clamped: List[str] = []

    # Prohibited use-type: no counteroffer exists — the door is closed, not narrowed.
    if req.use_type in policy.prohibited_use_types:
        return NegotiationOutcome(
            status="COUNTEROFFER_REJECTED_BY_POLICY",
            work_id=policy.work_id, counterparty_id=proposal.counterparty_id,
            offered_scope=None,
            clamped_dimensions=["use_type (prohibited)"],
            rationale=(f"Use type '{req.use_type}' is prohibited for this work; no "
                       "counteroffer can narrow a prohibited use into an allowed one."))

    # Use-type: clamp DOWN to the policy maximum if the request sits above it.
    # 'above' = the requested type is NOT contained by the policy max (the max
    # does not permit it), while the max IS a valid grant. Clamp to the max.
    use_type = req.use_type
    if not is_use_type_contained(policy.max_use_type, req.use_type):
        # synthesis is incomparable: a request for it against a non-synthesis
        # ceiling cannot be narrowed to fit, and vice versa.
        if not is_use_type_contained(req.use_type, policy.max_use_type):
            return NegotiationOutcome(
                status="COUNTEROFFER_REJECTED_BY_POLICY",
                work_id=policy.work_id, counterparty_id=proposal.counterparty_id,
                offered_scope=None,
                clamped_dimensions=[f"use_type ({req.use_type} incomparable to {policy.max_use_type})"],
                rationale=(f"Requested use type '{req.use_type}' is incomparable to the "
                           f"policy maximum '{policy.max_use_type}' — there is no narrower "
                           "scope that satisfies both."))
        use_type = policy.max_use_type
        clamped.append(f"use_type: {req.use_type} → {policy.max_use_type}")

    # Model class: if the policy restricts to a single class, clamp to it.
    model_class = req.model_class
    if policy.allowed_model_class != "all_models" and req.model_class != policy.allowed_model_class:
        model_class = policy.allowed_model_class
        clamped.append(f"model_class: {req.model_class} → {policy.allowed_model_class}")

    # Commercial: cannot exceed the policy.
    commercial = req.commercial
    if req.commercial and not policy.commercial_allowed:
        commercial = False
        clamped.append("commercial: true → false")

    # Territory: intersect. Policy WW allows anything; otherwise the offered
    # set is the intersection, and an empty intersection is a rejection.
    territory = list(req.territory or ["WW"])
    if "WW" not in policy.territory_allowed:
        requested = set(req.territory or ["WW"])
        if "WW" in requested:
            territory = list(policy.territory_allowed)
            clamped.append(f"territory: WW → {sorted(policy.territory_allowed)}")
        else:
            allowed = requested & set(policy.territory_allowed)
            if not allowed:
                return NegotiationOutcome(
                    status="COUNTEROFFER_REJECTED_BY_POLICY",
                    work_id=policy.work_id, counterparty_id=proposal.counterparty_id,
                    offered_scope=None,
                    clamped_dimensions=[f"territory ({sorted(requested)} ∩ "
                                        f"{sorted(policy.territory_allowed)} = ∅)"],
                    rationale="No requested territory is permitted for this work.")
            if allowed != requested:
                territory = sorted(allowed)
                clamped.append(f"territory: {sorted(requested)} → {sorted(allowed)}")

    # Attribution: policy can only ADD the obligation, never drop it.
    attribution = req.attribution_required or policy.attribution_always_required
    if policy.attribution_always_required and not req.attribution_required:
        clamped.append("attribution_required: false → true")

    # Duration: cap the requested window to the policy maximum.
    valid_until = req.valid_until
    if policy.max_duration_days is not None:
        from datetime import timedelta
        cap = req.valid_from + timedelta(days=policy.max_duration_days)
        if valid_until is None or valid_until > cap:
            valid_until = cap
            clamped.append(f"duration: capped to {policy.max_duration_days} days")

    offered = Scope(
        use_type=use_type, model_class=model_class, commercial=commercial,
        attribution_required=attribution, territory=territory,
        valid_from=req.valid_from, valid_until=valid_until)

    if not clamped:
        return NegotiationOutcome(
            status="AGREED", work_id=policy.work_id,
            counterparty_id=proposal.counterparty_id, offered_scope=offered,
            rationale="The proposal is within policy on every dimension.")
    return NegotiationOutcome(
        status="COUNTEROFFER", work_id=policy.work_id,
        counterparty_id=proposal.counterparty_id, offered_scope=offered,
        clamped_dimensions=clamped,
        rationale=("Counteroffer: the proposal has been narrowed to the artist's "
                   "policy on the dimensions listed. No economic term can widen it."))
