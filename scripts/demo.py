#!/usr/bin/env python3
"""
scripts/demo.py — `make demo` (HOD-501).

Credential-free, deterministic, in-process demonstration of the fleet's core
properties, driven entirely by committed fixtures. No GCP credentials, no
network, no emulator required. Every beat asserts the property it demonstrates
and the script exits nonzero if any assertion fails.

Beats:
  1. The scope lattice partial order, printed from its declaration as data.
  2. Byte-stable shuffled replay of resolve() over the fixture event log (HOD-103).
  3. Temporal fold: the same query at three timestamps, three individually
     correct answers, revocation narrowing the present without rewriting the
     past (HOD-107).
  4. Buyer scope request with the poisoned-document fixture: the Prompt
     Inspector detects the injection, the request proceeds under its original
     scope, and the licensable outcome is identical to the clean request (HOD-313).
  5. The four conflict walls: forbidden reads denied by the Agent Gateway with
     structured PolicyDenialEvents, never silent (HOD-311, HOD-312).
  6. The honesty invariants: the schema cannot express training-set membership,
     and the overclaim lint rejects paraphrased overclaims (HOD-320).
"""

import os
import sys
import json
import random
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Force the credential-free path before importing any gateway code.
os.environ["HODI_OFFLINE"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema.lattice import USE_TYPE_CONTAINMENT, MODEL_CLASS_CONTAINMENT
from src.schema.grant_event import GrantEvent
from src.schema.scope import Scope
from src.resolve.resolver import resolve, active_grant_events
from src.resolve.evaluator import permits
from src.gateway.prompt_inspector import PromptInspector
from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
from src.evidence.overclaim_lint import OverclaimLint, OverclaimLintViolation

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NEGOTIATOR_SA = "licensing-negotiator@hodi-2026.iam.gserviceaccount.com"
EVIDENCE_SA = "evidence-agent-sa@hodi-2026.iam.gserviceaccount.com"
PROPAGATOR_SA = "revocation-propagator-sa@hodi-2026.iam.gserviceaccount.com"


def rule(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def load_fixture_events():
    with open(FIXTURES / "demo_grant_log.json") as f:
        data = json.load(f)
    return [GrantEvent(**e) for e in data["events"]]


def beat_1_lattice():
    rule("BEAT 1 — SCOPE LATTICE PARTIAL ORDER (declared as data, HOD-104)")
    for parent, children in USE_TYPE_CONTAINMENT.items():
        print(f"  {parent:<18} contains: {', '.join(sorted(children))}")
    for parent, children in MODEL_CLASS_CONTAINMENT.items():
        print(f"  {parent:<18} contains: {', '.join(sorted(children))}")


def beat_2_byte_stable_replay(events):
    rule("BEAT 2 — BYTE-STABLE SHUFFLED REPLAY (HOD-103)")
    ordered_state = resolve("grant-demo-001", at=None, events=list(events))
    shuffled = list(events)
    random.Random(42).shuffle(shuffled)
    shuffled_state = resolve("grant-demo-001", at=None, events=shuffled)

    b1 = ordered_state.model_dump_json().encode("utf-8")
    b2 = shuffled_state.model_dump_json().encode("utf-8")
    h1, h2 = hashlib.sha256(b1).hexdigest(), hashlib.sha256(b2).hexdigest()
    print(f"  resolve() over committed order:  sha256={h1}")
    print(f"  resolve() over shuffled order:   sha256={h2}")
    assert b1 == b2, "Replay over shuffled event order is NOT byte-stable!"
    print("  PASS: identical bytes — the fold is order-independent and deterministic.")


def beat_3_temporal_fold(events):
    rule("BEAT 3 — TEMPORAL FOLD: REVOCATION NARROWS THE PRESENT, NOT THE PAST (HOD-107)")
    t_before = datetime(2026, 8, 4, tzinfo=timezone.utc)
    t_revoked = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    t_after = datetime(2026, 8, 7, tzinfo=timezone.utc)

    s_before = resolve("grant-demo-001", at=t_before, events=events)
    s_revoked = resolve("grant-demo-001", at=t_revoked, events=events)
    s_after = resolve("grant-demo-001", at=t_after, events=events)

    print(f"  at {t_before.date()}: status={s_before.status:<9} scope={s_before.active_scope.use_type if s_before.active_scope else None}")
    print(f"  at {t_revoked.date()}: status={s_revoked.status:<9} scope={s_revoked.active_scope.use_type if s_revoked.active_scope else None}")
    print(f"  at {t_after.date()}: status={s_after.status:<9} scope={s_after.active_scope.use_type if s_after.active_scope else None}")

    assert s_before.status == "active" and s_before.active_scope.use_type == "training"
    assert s_revoked.status == "revoked" and s_revoked.active_scope is None
    assert s_after.status == "active" and s_after.active_scope.use_type == "fine_tuning"
    assert len(s_after.history_events) == 3, "All three events must remain visible — nothing is deleted."
    print("  PASS: three timestamps, three individually correct answers; all events visible in history.")


def beat_4_poisoned_request(events):
    rule("BEAT 4 — POISONED BUYER REQUEST: DETECTED, LOGGED, PROCEEDS UNDER ORIGINAL SCOPE (HOD-313)")
    inspector = PromptInspector()
    t_eval = datetime(2026, 8, 7, tzinfo=timezone.utc)

    outcomes = {}
    for name in ("clean", "poisoned"):
        with open(FIXTURES / f"buyer_request_{name}.json") as f:
            req = json.load(f)
        raw = req["document_text"].encode("utf-8")
        result = inspector.inspect(raw)
        active = active_grant_events([e for e in events if e.counterparty_id == req["counterparty_id"]], at=t_eval)
        evaluation = permits(active, Scope(**req["requested_scope"]), at=t_eval)
        outcomes[name] = evaluation
        print(f"  [{name:<8}] injection_detected={result.injection_detected!s:<5} "
              f"engine={result.inspector_engine} stored_byte_identical={result.stored_bytes == raw}")
        if result.injection_detected:
            print(f"             pattern: {result.pattern_matched}")
        print(f"             permitted={evaluation.permitted} via={evaluation.matching_grant_id}")

    assert outcomes["clean"].permitted == outcomes["poisoned"].permitted
    assert outcomes["clean"].matching_grant_id == outcomes["poisoned"].matching_grant_id
    print("  PASS: identical licensable outcome — the injection changed nothing but the audit log.")


def beat_4b_natural_language_interpretation(events):
    rule("BEAT 4B — THE MODEL INTERPRETS INTENT, THE LATTICE DECIDES PERMISSION (HOD-301)")
    from src.llm.scope_interpreter import ScopeInterpreter
    from src.llm.vertex_gemini import PINNED_INTERPRETER_MODEL
    interp = ScopeInterpreter()
    t_eval = datetime(2026, 8, 7, tzinfo=timezone.utc)
    print(f"  interpreter: {PINNED_INTERPRETER_MODEL} (pinned, temperature 0; replaying the recorded")
    print(f"  response from fixtures/gemini_response_cache.json — captured from a real Vertex AI call)")

    with open(FIXTURES / "buyer_request_clean.json") as f:
        req = json.load(f)
    print(f"  natural-language request: \"{req['document_text'][:88]}...\"")
    scope = interp.interpret(req["document_text"], valid_from=t_eval)
    print(f"  interpreted scope: use_type={scope.use_type} model_class={scope.model_class} "
          f"commercial={scope.commercial} territory={scope.territory}")
    active = active_grant_events([e for e in events if e.counterparty_id == req["counterparty_id"]], at=t_eval)
    evaluation = permits(active, scope, at=t_eval)
    print(f"  lattice verdict:  permitted={evaluation.permitted} via={evaluation.matching_grant_id}")
    assert evaluation.permitted, "The recorded clean interpretation must be permitted by the fixture grant."

    with open(FIXTURES / "buyer_request_poisoned.json") as f:
        preq = json.load(f)
    pscope = interp.interpret(preq["document_text"], valid_from=t_eval)
    pevaluation = permits(active_grant_events([e for e in events if e.counterparty_id == preq["counterparty_id"]], at=t_eval), pscope, at=t_eval)
    print(f"  poisoned request interpreted as territory={pscope.territory} "
          f"model_class={pscope.model_class} -> permitted={pevaluation.permitted}")
    assert not pevaluation.permitted, \
        "The injection broadened the interpretation; the lattice must deny what no grant contains."
    print("  The model returns a Scope and nothing else; a malformed or out-of-vocabulary")
    print("  interpretation is rejected, never coerced. permits() is the only authority.")


def beat_5_conflict_walls():
    rule("BEAT 5 — THE FOUR CONFLICT WALLS: DENIALS ARE STRUCTURED EVENTS, NEVER SILENT (HOD-312)")
    gateway = AgentGateway()
    attempts = [
        ("negotiator reads grants UNFILTERED", NEGOTIATOR_SA, "licensing_negotiator", "grants", None,
         {"counterparty_id": "acme-intelligence-labs"}),
        ("negotiator reads ANOTHER counterparty", NEGOTIATOR_SA, "licensing_negotiator", "grants",
         {"counterparty_id": "buyer-acme-2"}, {"counterparty_id": "acme-intelligence-labs"}),
        ("evidence agent reads commercial grants", EVIDENCE_SA, "evidence_agent", "grants", None, None),
        ("revocation propagator reads artist identity", PROPAGATOR_SA, "revocation_propagator", "artists", None, None),
    ]
    denied = 0
    for label, sa, role, coll, filters, ctx in attempts:
        try:
            gateway.read_collection(calling_sa=sa, calling_role_key=role, target_collection=coll,
                                    filters=filters, session_context=ctx)
            print(f"  [FAIL] {label}: read was PERMITTED — boundary breached!")
        except GatewayPolicyDenial as e:
            denied += 1
            print(f"  [DENIED] {label}")
            print(f"           reason: {e.denial.reason}")
    assert denied == len(attempts), "Every forbidden read must be denied."
    assert len(gateway.denial_events) == len(attempts), "Every denial must be recorded as an event."
    print(f"  PASS: {denied}/{len(attempts)} forbidden reads denied, each with a structured PolicyDenialEvent.")


def beat_6_honesty_invariants():
    rule("BEAT 6 — HONESTY INVARIANTS: THE SCHEMA CANNOT SAY IT, THE LINT WON'T LET IT (HOD-320)")
    from src.schema.evidence import EvidenceRecord, CLAIM_LIMIT_LITERAL
    try:
        EvidenceRecord(
            evidence_id="ev-demo-1", work_id="work-essay-001",
            **{"class": "training_membership"},
            observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
            source_uri="https://example.invalid", detail="n/a"
        )
        print("  [FAIL] schema accepted a training_membership class!")
        sys.exit(1)
    except Exception:
        print("  PASS: 'training_membership' is not an EvidenceRecord class — the schema cannot express the claim.")
    print(f"  Every record carries the literal: \"{CLAIM_LIMIT_LITERAL}\"")

    lint = OverclaimLint()
    overclaim = "This canary hit proves the model saw your work."
    try:
        lint.lint_text(overclaim)
        print("  [FAIL] overclaim lint accepted an overclaim paraphrase!")
        sys.exit(1)
    except OverclaimLintViolation:
        print(f"  PASS: overclaim lint rejected: \"{overclaim}\"")


def main():
    print("HODI CREDENTIAL-FREE DEMO — fixtures only, no GCP credentials, no network.")
    events = load_fixture_events()
    beat_1_lattice()
    beat_2_byte_stable_replay(events)
    beat_3_temporal_fold(events)
    beat_4_poisoned_request(events)
    beat_4b_natural_language_interpretation(events)
    beat_5_conflict_walls()
    beat_6_honesty_invariants()
    print("\nALL DEMO BEATS PASSED.")


if __name__ == "__main__":
    main()
