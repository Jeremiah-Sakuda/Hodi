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


class DemoAssertionError(AssertionError):
    """Raised when a demo beat's property does not hold."""


def require(condition: bool, message: str) -> None:
    """
    Assert a demo property WITHOUT the `assert` statement.

    `python3 -O` strips `assert`, and this script is the sole offline guard for
    invariants no unit test covers. Under -O the demo would print visibly
    contradictory output and still finish with "ALL DEMO BEATS PASSED."
    """
    if not condition:
        raise DemoAssertionError(message)


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
    require(b1 == b2, "Replay over shuffled event order is NOT byte-stable!")
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

    require(s_before.status == "active" and s_before.active_scope.use_type == "training", "demo property failed")
    require(s_revoked.status == "revoked" and s_revoked.active_scope is None, "demo property failed")
    require(s_after.status == "active" and s_after.active_scope.use_type == "fine_tuning", "demo property failed")
    require(len(s_after.history_events) == 3, "All three events must remain visible — nothing is deleted.")
    print("  PASS: three timestamps, three individually correct answers; all events visible in history.")


def beat_4_poisoned_request(events):
    rule("BEAT 4 — POISONED BUYER REQUEST: DETECTED, LOGGED, PROCEEDS UNDER ORIGINAL SCOPE (HOD-313)")
    inspector = PromptInspector()
    t_eval = datetime(2026, 8, 7, tzinfo=timezone.utc)

    outcomes, detections, byte_identical = {}, {}, {}
    for name in ("clean", "poisoned"):
        with open(FIXTURES / f"buyer_request_{name}.json") as f:
            req = json.load(f)
        raw = req["document_text"].encode("utf-8")
        result = inspector.inspect(raw)
        # The authorization tuple is principal × work × scope × time (HOD-701):
        # the active set handed to permits() is scoped to BOTH the fixture's
        # counterparty and its work_id, exactly as the deployed handler scopes
        # its gateway read.
        active = active_grant_events(
            [e for e in events
             if e.counterparty_id == req["counterparty_id"] and e.work_id == req["work_id"]],
            at=t_eval)
        evaluation = permits(active, Scope(**req["requested_scope"]), at=t_eval)
        outcomes[name] = evaluation
        detections[name] = result.injection_detected
        byte_identical[name] = (result.stored_bytes == raw)
        print(f"  [{name:<8}] injection_detected={result.injection_detected!s:<5} "
              f"engine={result.inspector_engine} stored_byte_identical={result.stored_bytes == raw}")
        if result.injection_detected:
            print(f"             pattern: {result.pattern_matched}")
        print(f"             permitted={evaluation.permitted} via={evaluation.matching_grant_id}")

    # These two assertions are the ones that can actually fail if the inspector
    # dies: comparing the two licensable outcomes alone cannot, because they are
    # identical whether or not detection works.
    require(detections["clean"] is False, "Clean document must not be flagged.")
    require(detections["poisoned"] is True, "Poisoned document MUST be detected.")
    require(byte_identical["poisoned"] is True, "Stored bytes must be byte-identical to received.")
    require(outcomes["clean"].permitted == outcomes["poisoned"].permitted, "demo property failed")
    require(outcomes["clean"].matching_grant_id == outcomes["poisoned"].matching_grant_id, "demo property failed")
    print("  PASS: injection detected, document stored byte-identical, and the licensable")
    print("        outcome is unchanged — the injection altered nothing but the audit log.")


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
    require(evaluation.permitted, "The recorded clean interpretation must be permitted by the fixture grant.")

    with open(FIXTURES / "buyer_request_poisoned.json") as f:
        preq = json.load(f)
    pscope = interp.interpret(preq["document_text"], valid_from=t_eval)
    pevaluation = permits(active_grant_events([e for e in events if e.counterparty_id == preq["counterparty_id"]], at=t_eval), pscope, at=t_eval)
    print(f"  poisoned request interpreted as territory={pscope.territory} "
          f"model_class={pscope.model_class} -> permitted={pevaluation.permitted}")
    require(not pevaluation.permitted,  "The injection broadened the interpretation; the lattice must deny what no grant contains.")
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
    require(denied == len(attempts), "Every forbidden read must be denied.")
    require(len(gateway.denial_events) == len(attempts), "Every denial must be recorded as an event.")
    print(f"  PASS: {denied}/{len(attempts)} forbidden reads denied, each with a structured PolicyDenialEvent.")


def beat_5b_adk_delegation(events):
    rule("BEAT 5B — ADK FLEET DELEGATION: THREE SERVICE ACCOUNTS, ONE TRACE (HOD-302/330/340)")
    import io
    from contextlib import redirect_stdout
    from src.fleet.adk_fleet import run_revocation_delegation

    # The console span exporter is noisy; the assertions below are the proof.
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = run_revocation_delegation(
            counterparty_id="acme-intelligence-labs",
            work_id="work-essay-001",
            # work-essay-001's active grant is fine_tuning (re-granted in Beat 2);
            # revoking fine_tuning terminates it because it PERMITS fine_tuning.
            # Revoking training would (correctly) affect nothing here — that grant
            # never permitted training.
            revoked_use_type="fine_tuning",
            fallback_events=events,
        )

    for entry in result["transcript"]:
        print(f"  [{entry['author']:<22}] {entry['text']}")

    require(result["negotiator_discovered"] == [],  "A buyer's negotiator must not be told the revocation propagator exists.")
    require(result["discovered"] == ["revocation_propagator-v1"],  "The artist's rights custodian must be able to discover the propagator by role.")
    require(result["cascade"] is not None and result["cascade"].affected_grants,  "The discovered propagator must have executed the cascade.")
    print("  PASS: agent-to-agent addressing goes through role-scoped registry discovery —")
    print("        denied for the negotiator, granted for the custodian — and the cascade ran")
    print("        under a third service account holding neither identity nor buyer terms.")


def beat_5c_quarantine_and_reroute(events):
    rule("BEAT 5C — A LOOPING WORKER IS QUARANTINED, THE REQUEST STILL COMPLETES (HOD-341/342)")
    import io
    from contextlib import redirect_stdout
    from src.supervisor.supervisor import Supervisor
    from src.fleet.adk_fleet import run_revocation_delegation

    buf = io.StringIO()
    with redirect_stdout(buf):
        # Fault injection: the revocation propagator never returns.
        result = run_revocation_delegation(
            counterparty_id="acme-intelligence-labs",
            work_id="work-essay-001",
            revoked_use_type="training",
            fallback_events=events,
            supervisor=Supervisor(deadline_seconds=0.5),
            loop_forever=True,
        )

    for entry in result["transcript"][-2:]:
        print(f"  [{entry['author']:<22}] {entry['text']}")

    abandoned = result["task_abandoned_events"]
    quarantine = result["quarantine"]
    require(len(abandoned) == 1 and abandoned[0]["written_by"] == "supervisor",  "TaskAbandoned must be written BY THE SUPERVISOR, not by the failing worker.")
    require(abandoned[0]["reason"] == "deadline_exceeded", "demo property failed")
    require(quarantine["deregistered"] is True, "The looping worker must be deregistered.")
    require(result["post_quarantine_discovery"] == [],  "It must stay deregistered for the remainder of the run.")
    require(quarantine["result"]["status"] == "COMPLETED_DEGRADED",  "The request must still complete.")
    require(quarantine["result"]["notices_issued"] == 0, "demo property failed")

    print(f"  TaskAbandoned written by : {abandoned[0]['written_by']} (reason: {abandoned[0]['reason']})")
    print(f"  discovery after quarantine: {result['post_quarantine_discovery']} (deregistered for the run)")
    print("  PASS: the worker looped, the supervisor abandoned it without its cooperation,")
    print("        the registry deregistered it, and the request completed as a STATED")
    print("        partial result — no notices issued, nothing appended to the log.")


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


def beat_7_consent_incident():
    rule("BEAT 7 — AUTONOMOUS CONSENT INCIDENT: OBSERVE, INVESTIGATE, ADJUDICATE, CONTAIN, PROVE (HOD-703/704/705/706)")
    import copy
    from src.gateway.gateway import AgentGateway, GatewayPolicyDenial
    from src.incident.engine import IncidentEngine
    from src.incident.package import export_package, verify_package
    from src.schema.assertion import TypedAssertion
    from src.schema import signing
    from pydantic import ValidationError

    fixture = json.loads((FIXTURES / "incident_scenario.json").read_text())

    # The demo's signer is EPHEMERAL and says so in every envelope — it
    # proves the mechanism (sign → verify → tamper detection) offline, never
    # durable authority. Cleared afterwards so later beats stay unchanged.
    os.environ["HODI_SIGNING"] = "ephemeral"
    signing._active_signer = None
    try:
        gateway = AgentGateway(offline_reads={
            "crawler_access": [fixture["access_record"]],
            "works": [fixture["work"]],
            "grants": [],
        })

        # 7a — the epistemic wall, before anything runs: an agent claiming
        # beyond its authority is refused as a structured denial, and the
        # training claim cannot even be CONSTRUCTED as data. Demonstrated on
        # a THROWAWAY gateway so the incident's own gateway can prove the
        # cleaner thing afterwards: zero denials, because no wall was even
        # attempted during the real investigation.
        demo_wall_gateway = AgentGateway()
        try:
            demo_wall_gateway.submit_assertion(
                calling_sa="evidence-agent-sa@hodi-2026.iam.gserviceaccount.com",
                calling_role_key="evidence_agent",
                assertion=TypedAssertion(
                    assertion_id="a-demo", assertion_class="GRANT_EXISTED",
                    asserted_by_role="evidence_agent",
                    subject_work_id=fixture["work"]["work_id"],
                    basis="overreach", recorded_at=datetime.now(timezone.utc)))
            print("  [FAIL] the evidence agent asserted outside its authority!")
            sys.exit(1)
        except GatewayPolicyDenial as e:
            print(f"  PASS: assertion authority denied — {e.denial.policy_consulted}: "
                  f"evidence_agent may not claim GRANT_EXISTED")
        try:
            TypedAssertion(assertion_id="a", assertion_class="MODEL_TRAINED_ON_WORK",
                           asserted_by_role="evidence_agent",
                           subject_work_id="w", basis="b",
                           recorded_at=datetime.now(timezone.utc))
            print("  [FAIL] the schema constructed a training-membership assertion!")
            sys.exit(1)
        except ValidationError:
            print("  PASS: MODEL_TRAINED_ON_WORK is not an assertion class — the claim is inexpressible as data.")

        # 7b — the incident itself: a FICTIONAL scraper fetched the work.
        result = IncidentEngine(gateway=gateway).run(
            work_id=fixture["work"]["work_id"],
            declared_principal=fixture["declared_principal"],
            access_record=fixture["access_record"])
        statuses = {f.claim: f.status for f in result.manifest.decision.findings}
        assert statuses["ACCESS_OUTSIDE_DECLARED_POLICY"] == "ESTABLISHED"
        training = result.manifest.decision.not_determinable["MODEL_TRAINING_OCCURRED"]
        assert training.startswith("NOT_ESTABLISHED")
        assert gateway.denial_events == [], "a wall was attempted during the investigation"
        print(f"  PASS: {[e.status for e in result.lifecycle]} — every transition an appended event")
        print("  PASS: ACCESS_OUTSIDE_DECLARED_POLICY: ESTABLISHED "
              f"(basis: {len(result.assertions)} typed assertions, walls intact)")
        print("  PASS: MODEL_TRAINING_OCCURRED: NOT_ESTABLISHED — carried on the decision itself")
        assert result.freeze is not None
        print(f"  PASS: containment = negotiation freeze {result.freeze.freeze_id} "
              "(the rail, not a weapon: nothing to revoke, nothing revoked)")

        # 7c — the record proves itself: verify, then tamper one byte.
        package = export_package(result)
        report = verify_package(package)
        assert report.all_ok, [l for ok, l in report.checks if not ok]
        print(f"  PASS: package verifies — {len(report.checks)} checks including "
              "decision REPRODUCED from the packaged assertions")
        tampered = copy.deepcopy(package)
        tampered["manifest"]["subject_principal"] = "an-innocent-party"
        assert not verify_package(tampered).all_ok
        print("  PASS: one tampered field and verification fails "
              f"(signature: {package['manifest']['signature'].split(':', 1)[0]} — labelled ephemeral)")
    finally:
        os.environ.pop("HODI_SIGNING", None)
        signing._active_signer = None


def main():
    print("HODI CREDENTIAL-FREE DEMO — fixtures only, no GCP credentials, no network.")
    events = load_fixture_events()
    beat_1_lattice()
    beat_2_byte_stable_replay(events)
    beat_3_temporal_fold(events)
    beat_4_poisoned_request(events)
    beat_4b_natural_language_interpretation(events)
    beat_5_conflict_walls()
    beat_5b_adk_delegation(events)
    beat_5c_quarantine_and_reroute(events)
    beat_6_honesty_invariants()
    beat_7_consent_incident()
    print("\nALL DEMO BEATS PASSED.")


if __name__ == "__main__":
    main()
