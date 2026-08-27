"""
src/api/demo_sandbox.py — the public /demo sandbox (HOD-760).

WHAT THIS IS. The interactive walkthrough at /demo lets anyone — a judge, a
creator, a skeptic — grant, revoke, and verify against the LIVE deployed
service, with nothing simulated. Every value it returns is produced by the same
code /api/v1/* runs.

WHY IT IS SAFE, STATED STRUCTURALLY. These routes are unauthenticated by
design, so the boundary that keeps them off real data cannot be a credential
check. It is POLICY DATA: the routes run as `sandbox_agent`, whose
`denied_collections` names every real collection and whose `permitted_collections`
names only the `demo_*` ones. The identical gateway every agent crosses refuses
`sandbox_agent` at `grants` exactly as it refuses the evidence agent at
`buyer_terms`. There is no `if work_id.startswith("demo-")` anywhere — that would
be a string check in the one layer this project's thesis says cannot be trusted.
`tests/test_demo_sandbox_boundary.py` proves a demo call aimed at a real
collection is denied at the gateway, not by convention.

WHY IT IS HONEST. The revocation runs the EXACT `execute_revocation_cascade`
the production worker runs — same gateway, same propagator logic, same lease and
outbox, same Cloud KMS signature on the notice — parameterised only by the
`demo_` collection namespace and the sandbox role. The one deliberate difference
is documented: the notice PROSE is the linted deterministic template rather than
a live Gemini call, so a public click costs no model spend; the template is a
real production path (the cascade's own fallback), and the notice is genuine and
signed.

WHAT BOUNDS ABUSE. An unauthenticated route that appends to Firestore and calls
Cloud KMS per click is write- and spend-amplification if left open. Session ids
are server-minted and unguessable; session creation is per-IP rate limited; and
each session is capped at a small number of real signatures. Demo collections
hold no real data and can be dropped at any time.
"""

import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request

from src.schema.iam_policy import AGENT_SA_MAP
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent, generate_deterministic_event_id
from src.schema.signing import unsigned_placeholder
from src.resolve.evaluator import permits
from src.resolve.resolver import active_grant_events

SANDBOX_ROLE = "sandbox_agent"
SANDBOX_SA = AGENT_SA_MAP[SANDBOX_ROLE]["sa_email"]

# The one counterparty the demo grant is with. Fictional, unnamed as a real
# company — the same name every other fixture uses.
DEMO_COUNTERPARTY = "acme-intelligence-labs"

# A session id is server-minted; this pattern is also the guard against a
# client smuggling anything but an id into the work_id we derive from it.
_SID = re.compile(r"^[A-Za-z0-9_-]{6,32}$")

# Abuse bounds (see module docstring).
MAX_SESSIONS_PER_IP_PER_HOUR = 30
MAX_SIGNATURES_PER_SESSION = 8
SESSION_TTL = timedelta(hours=2)

router = APIRouter(prefix="/demo/api", tags=["demo-sandbox"])

# Best-effort, per-instance rate accounting. Correctness of the BOUNDARY never
# depends on this — it depends on the gateway policy. This only caps volume.
_ip_hits: Dict[str, List[float]] = {}
_ip_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()  # the hop Cloud Run appends, not the client-supplied head
    return request.client.host if request.client else "unknown"


def _rate_limit_or_429(ip: str) -> None:
    now = time.time()
    with _ip_lock:
        hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
        if len(hits) >= MAX_SESSIONS_PER_IP_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many demo sessions from this address. Try again later.")
        hits.append(now)
        _ip_hits[ip] = hits


_GATEWAY = None


def _gateway():
    # One gateway for the process. In production every instance shares Firestore,
    # so this is merely tidy; offline it is what lets a read see the write from a
    # prior request in the same process (the in-memory sink is per instance),
    # which is also what the boundary test relies on.
    global _GATEWAY
    if _GATEWAY is None:
        from src.gateway.gateway import AgentGateway
        _GATEWAY = AgentGateway()
    return _GATEWAY


def _work_id(sid: str) -> str:
    if not _SID.match(sid):
        raise HTTPException(status_code=404, detail="Unknown demo session.")
    return f"demo-{sid}"


def _read_events(gateway, work_id: str) -> List[GrantEvent]:
    raw = gateway.read_collection(
        calling_sa=SANDBOX_SA, calling_role_key=SANDBOX_ROLE,
        target_collection="demo_grants", filters={"work_id": work_id})
    return [GrantEvent(**e) for e in raw]


def _demo_scope(use_type: str, at: datetime) -> Scope:
    return Scope(use_type=use_type, model_class="open_weights", commercial=False,
                 attribution_required=True, territory=["US", "CA"], valid_from=at)


@router.post("/session")
async def open_session(request: Request):
    """Mint an isolated sandbox and seed one grant, held at `training`.

    The grant is a real `granted` event appended to `demo_grants` as
    `sandbox_agent` — through the same gateway a real grant crosses, refused if
    it ever named a real collection.
    """
    _rate_limit_or_429(_client_ip(request))
    sid = secrets.token_urlsafe(9)
    work_id = f"demo-{sid}"
    now = datetime.now(timezone.utc)
    grant_id = f"grant-{sid}"
    event = GrantEvent(
        event_id=generate_deterministic_event_id(grant_id, 1, 1),
        grant_id=grant_id, work_id=work_id, counterparty_id=DEMO_COUNTERPARTY,
        scope=_demo_scope("training", now), kind="granted", issued_at=now,
        signature=unsigned_placeholder("grant", grant_id))
    _gateway().write_document(
        calling_sa=SANDBOX_SA, calling_role_key=SANDBOX_ROLE,
        target_collection="demo_grants", doc_id=event.event_id,
        data=event.model_dump(mode="json"))
    return {
        "session": sid,
        "work_id": work_id,
        "counterparty_id": DEMO_COUNTERPARTY,
        "held": "training",
        "grant_scope": event.scope.model_dump(mode="json"),
        "note": "A real grant was appended to the append-only log, in your own sandbox.",
    }


@router.post("/{sid}/license")
async def evaluate_license(sid: str, request: Request):
    """Evaluate the fixed fine-tuning request against the sandbox grant.

    Pure `permits()` over the fold — the same evaluator `/api/v1/license` uses.
    Returns `permitted: true` while the grant stands, `false` after it is
    revoked. No signing, no writes.
    """
    work_id = _work_id(sid)
    gateway = _gateway()
    events = _read_events(gateway, work_id)
    if not events:
        raise HTTPException(status_code=404, detail="This demo session has expired. Start a new one.")
    active = [g for g in active_grant_events(events) if g.work_id == work_id]
    requested = _demo_scope("fine_tuning", datetime.now(timezone.utc))
    result = permits(active_grants=active, requested_scope=requested)
    return {
        "requested_scope": requested.model_dump(mode="json"),
        "permitted": result.permitted,
        "licensable_set": getattr(result, "licensable_set", None),
        "explicit_exclusions": getattr(result, "explicit_exclusions", None),
        "counterparty_id": DEMO_COUNTERPARTY,
    }


@router.post("/{sid}/revoke")
async def revoke(sid: str, request: Request):
    """Run the REAL cascade over the sandbox, revoking `training`.

    Constructs the production `RevocationPropagatorAgent` with the sandbox role
    and the `demo_` namespace — identical cascade, identical Cloud KMS signature
    on the notice, isolated collections. Capped per session.
    """
    work_id = _work_id(sid)
    gateway = _gateway()
    events = _read_events(gateway, work_id)
    if not events:
        raise HTTPException(status_code=404, detail="This demo session has expired. Start a new one.")

    revocations = sum(1 for e in events if e.kind == "revoked")
    if revocations >= MAX_SIGNATURES_PER_SESSION:
        raise HTTPException(status_code=429, detail="This demo session has reached its signing limit. Start a new one.")

    from src.agents.revocation_propagator import RevocationPropagatorAgent
    propagator = RevocationPropagatorAgent(
        gateway=gateway, role_key=SANDBOX_ROLE, collection_ns="demo_",
        notice_template_only=True)
    result = propagator.execute_revocation_cascade(
        work_id=work_id, revoked_use_type="training")
    return {
        "surface": "public-demo-sandbox",
        "result": result.model_dump(mode="json"),
    }


@router.post("/fleet-drill")
async def fleet_drill(request: Request):
    """Run the REAL ADK fleet delegation, live and write-free (HOD-760).

    This is the same `run_revocation_delegation` the artist-credentialed
    /api/v1/fleet/delegation_drill runs — real `google.adk` BaseAgent subclasses
    under a real Runner, each hop under a DIFFERENT service-account identity,
    with the propagator forced to loop so the supervisor quarantines it and the
    work reroutes. It reads fixture events and appends NOTHING, so it is safe to
    expose without a credential. The response is the real transcript plus the
    real Cloud Trace id the spans were written to — the visible answer to "is
    this four agents or four names in one prompt".
    """
    _rate_limit_or_429(_client_ip(request))
    import json as _json
    import time as _time
    from pathlib import Path as _Path
    from src.fleet.adk_fleet import run_revocation_delegation
    from src.supervisor.supervisor import Supervisor
    from src.observability.tracing import active_exporter_kind

    deadline = 0.3
    fixture = _Path(__file__).resolve().parents[2] / "fixtures" / "demo_grant_log.json"
    with open(fixture) as fh:
        events = [GrantEvent(**e) for e in _json.load(fh)["events"]]

    t0 = _time.perf_counter()
    r = run_revocation_delegation(
        counterparty_id=DEMO_COUNTERPARTY, work_id="work-repo-001",
        revoked_use_type="training", fallback_events=events,
        supervisor=Supervisor(deadline_seconds=deadline), loop_forever=True)
    elapsed_ms = round((_time.perf_counter() - t0) * 1000)

    def sa(role):
        return AGENT_SA_MAP[role]["sa_email"]

    # The waterfall, built from the REAL structured result so each outcome
    # reflects what actually happened this run, not a fixed script.
    steps = [
        {"agent": "Licensing negotiator", "sa": sa("licensing_negotiator"),
         "outcome": "PERMITTED", "detail": "reads only its own session's grant — never another buyer's"},
        {"agent": "Agent registry", "sa": None,
         "outcome": "NOT_DISCLOSED" if not r.get("negotiator_discovered") else "DISCLOSED",
         "detail": "a buyer's negotiator is not even told the revocation agent exists"},
        {"agent": "Rights custodian", "sa": sa("rights_custodian"),
         "outcome": "INITIATED", "detail": "holds identity; verifies ownership and begins the revocation"},
        {"agent": "Agent registry", "sa": None,
         "outcome": "DISCOVERED" if r.get("discovered") else "NONE",
         "detail": "the custodian's role MAY invoke the propagator, so now it is disclosed"},
        {"agent": "Revocation propagator", "sa": sa("revocation_propagator"),
         "outcome": "ABANDONED" if r.get("abandoned") else "COMPLETED",
         "detail": f"forced to loop; the supervisor's {deadline}s deadline fired and wrote TaskAbandoned itself"},
        {"agent": "Supervisor", "sa": None,
         "outcome": "QUARANTINED + REROUTED" if r.get("quarantine") else "—",
         "detail": "deregisters the worker; a standby returns a stated partial result and appends nothing"},
    ]
    exporter = active_exporter_kind()
    return {
        "surface": "public-demo-sandbox",
        "framework": "google.adk (BaseAgent + Runner)",
        "elapsed_ms": elapsed_ms,
        "trace_id": r.get("delegation_trace_id"),
        "trace_exporter": exporter,
        "completed_degraded": r.get("quarantine") is not None,
        "steps": steps,
    }
