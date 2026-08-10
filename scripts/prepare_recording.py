#!/usr/bin/env python3
"""
scripts/prepare_recording.py — put the live system into exactly the state
docs/VIDEO-SCRIPT.md assumes, and prove it did (HOD-510).

WHY THIS EXISTS. The hero beat revokes something. After take 1 the state is
wrong for take 2, and the cascade's cost depends on state in a way that is not
visible from the terminal: it makes one Gemini notice-drafting call per affected
grant, and a grant whose notice prompt is absent from the committed response
cache adds ~4.7 s of live model latency. Two affected grants is a reproducible
~5.3 s instead of ~0.5 s. Every verification run drifts the log further. An
enumeration you must remember to re-run is not a mechanism, so this is a script.

    make recording-prep     full pre-flight, run once before the first take
    make recording-reset    fast reset, run between takes

TARGET STATE
  1. grant-acme-il-001 ACTIVE          (the demo grant the hero revokes)
  2. grant-seed-2 REVOKED              (keeps the affected set at 1 = the fast path)
  3. throwaway '*-verify-*' credentials INACTIVE
  4. affected set for (work-repo-001, training) == 1
  5. that one grant's notice prompt PRESENT in the committed cache

It reports every one of those as OBSERVED, not assumed, and exits non-zero if
the state it cannot fix is wrong.

WHAT IT WILL NOT TOUCH. The `works` collection. `scripts/seed_firestore.py`
rewrites works and would drop the proof URIs `make verify-manifest` checks, so
this script only ever writes `grants` events and flips credential `active`
flags. Revoking grant-seed-2 is an append, never a delete — the log stays
append-only and the whole history remains visible.
"""

import argparse
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore

from src.api.auth import CREDENTIAL_COLLECTION
from src.llm.notice_drafter import DRAFT_PROMPT_TEMPLATE
from src.llm.vertex_gemini import PINNED_INTERPRETER_MODEL, _cache_key, _load_cache
from src.resolve.resolver import resolve
from src.schema.grant_event import GrantEvent
from src.schema.lattice import USE_TYPE_CONTAINMENT
from src.schema.scope import Scope

# The exact identifiers docs/VIDEO-SCRIPT.md names. Kept here rather than in the
# doc so the script and the shot list cannot disagree about what "ready" means.
HERO_WORK = "work-repo-001"
HERO_USE_TYPE = "training"
DEMO_GRANT = "grant-acme-il-001"
RIVAL_GRANT = "grant-seed-2"
RIVAL_COUNTERPARTY = "buyer-acme-2"
THROWAWAY_MARKER = "-verify-"

OK, BAD, INFO = "  [OK]  ", "  [!!]  ", "  [--]  "


def build_client(project_id: str) -> firestore.Client:
    """ADC first; falls back to the gcloud CLI token for local shells without ADC."""
    try:
        return firestore.Client(project=project_id)
    except Exception:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        from google.oauth2 import credentials as oauth2_credentials
        return firestore.Client(project=project_id,
                                credentials=oauth2_credentials.Credentials(token))


def work_events(db, work_id: str) -> list:
    raw = db.collection("grants").where(filter=firestore.FieldFilter("work_id", "==", work_id)).stream()
    return [GrantEvent(**d.to_dict()) for d in raw]


def grant_status(events: list, grant_id: str) -> str:
    return resolve(grant_id, events=events).status


def notice_is_cached(grant_id: str, work_id: str, counterparty_id: str) -> bool:
    """
    Exactly the lookup NoticeDrafter will perform: the same prompt template, the
    same pinned model, the same key function. Anything less would be a guess
    about the number this script exists to report.
    """
    prompt = DRAFT_PROMPT_TEMPLATE.format(
        grant_id=grant_id, work_id=work_id, counterparty_id=counterparty_id)
    return _cache_key(PINNED_INTERPRETER_MODEL, prompt) in _load_cache().get("entries", {})


def affected_set(events: list, revoked_use_type: str) -> list:
    """
    The propagator's own selection rule, read-only: fold each grant, keep the
    active ones whose use_type the revoked type contains. Replicated rather than
    called because execute_revocation_cascade() writes.
    """
    derived = USE_TYPE_CONTAINMENT.get(revoked_use_type, {revoked_use_type})
    out = []
    for gid in sorted({e.grant_id for e in events}):
        state = resolve(gid, events=events)
        if state.status == "active" and state.active_scope and state.active_scope.use_type in derived:
            out.append((gid, state.counterparty_id, state.active_scope.use_type))
    return out


def seed_demo_grant(db) -> None:
    """Delegates to the committed seeder so there is one definition of the demo grant."""
    from scripts.seed_demo_grant import seed_demo_grant as _seed
    _seed()


def revoke_rival(db, events: list) -> bool:
    """Append a revoking event for grant-seed-2 if the fold says it is active."""
    if grant_status(events, RIVAL_GRANT) != "active":
        return False
    state = resolve(RIVAL_GRANT, events=events)
    now = datetime.now(timezone.utc)
    ev = GrantEvent(
        event_id=str(uuid.uuid4()), grant_id=RIVAL_GRANT, work_id=HERO_WORK,
        counterparty_id=state.counterparty_id or RIVAL_COUNTERPARTY,
        scope=state.active_scope, kind="revoked", issued_at=now, signature="SIG_REVOKED")
    db.collection("grants").document(ev.event_id).set(ev.model_dump())
    return True


def regrant_rival(db) -> str:
    """The documented re-grant mechanism: a new `granted` event that supersedes."""
    now = datetime.now(timezone.utc)
    ev = GrantEvent(
        event_id=str(uuid.uuid4()), grant_id=RIVAL_GRANT, work_id=HERO_WORK,
        counterparty_id=RIVAL_COUNTERPARTY, kind="granted", issued_at=now,
        signature="sig-seed-2",
        scope=Scope(use_type="training", model_class="all_models", derivative_retention=True,
                    attribution_required=True, commercial=True, valid_from=now, valid_until=None))
    db.collection("grants").document(ev.event_id).set(ev.model_dump())
    return ev.event_id


def sweep_credentials(db) -> tuple:
    """Deactivate throwaway keys; return (deactivated, other_active) — never guess
    about a credential this script did not create."""
    deactivated, other_active = [], []
    for doc in db.collection(CREDENTIAL_COLLECTION).stream():
        rec = doc.to_dict()
        active = rec.get("active", False)
        if THROWAWAY_MARKER in doc.id:
            if active:
                doc.reference.update({"active": False})
                deactivated.append(doc.id)
        elif active:
            other_active.append((doc.id, rec.get("principal_type", "counterparty"),
                                 rec.get("counterparty_id")))
    return deactivated, other_active


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--between-takes", action="store_true",
                    help="fast reset: grants only, no credential sweep, no live probe")
    ap.add_argument("--two-counterparty", action="store_true",
                    help="re-grant grant-seed-2 so the cascade reaches two counterparties "
                         "(costs ~5.3 s per take instead of ~0.5 s)")
    args = ap.parse_args()

    if os.environ.get("HODI_OFFLINE") == "1":
        print("HODI_OFFLINE=1 — this script writes to live Firestore. Refusing.", file=sys.stderr)
        return 2

    project_id = os.environ.get("GCP_PROJECT_ID", "hodi-2026")
    mode = "BETWEEN-TAKES RESET" if args.between_takes else "PRE-FLIGHT"
    print("=" * 78)
    print(f"RECORDING {mode} — project '{project_id}'")
    print("=" * 78)

    db = build_client(project_id)
    failures = []

    # ---- 1. the demo grant --------------------------------------------------
    print("\n[1] demo grant")
    seed_demo_grant(db)

    # ---- 2. the rival grant -------------------------------------------------
    print("\n[2] rival grant (drives the affected-set size)")
    events = work_events(db, HERO_WORK)
    if args.two_counterparty:
        if grant_status(events, RIVAL_GRANT) == "active":
            print(f"{OK}{RIVAL_GRANT} already active — two-counterparty cascade")
        else:
            print(f"{INFO}re-granted {RIVAL_GRANT} as {regrant_rival(db)}")
    else:
        if revoke_rival(db, events):
            print(f"{INFO}{RIVAL_GRANT} was active — appended a revoking event")
        else:
            print(f"{OK}{RIVAL_GRANT} already revoked")

    # ---- 3. credentials -----------------------------------------------------
    if not args.between_takes:
        print("\n[3] credentials")
        deactivated, other_active = sweep_credentials(db)
        for k in deactivated:
            print(f"{INFO}deactivated throwaway credential '{k}'")
        if not deactivated:
            print(f"{OK}no active throwaway ('{THROWAWAY_MARKER}') credentials")
        print(f"{INFO}active credentials you will sign with:")
        for key_id, ptype, cp in sorted(other_active):
            print(f"          {key_id:24} {ptype:13} -> {cp}")
        if not any(p == "artist" for _, p, _ in other_active):
            failures.append("no ACTIVE artist credential — the hero's Frame B cannot be signed")
        if not any(p == "counterparty" for _, p, _ in other_active):
            failures.append("no ACTIVE counterparty credential — Frames A and C cannot be signed")

    # ---- 4. the numbers the beat depends on ---------------------------------
    print("\n[4] state the shot list assumes")
    events = work_events(db, HERO_WORK)
    demo_status = grant_status(events, DEMO_GRANT)
    rival_status = grant_status(events, RIVAL_GRANT)
    print(f"{OK if demo_status == 'active' else BAD}{DEMO_GRANT:20} {demo_status}")
    print(f"{INFO}{RIVAL_GRANT:20} {rival_status}")
    if demo_status != "active":
        failures.append(f"{DEMO_GRANT} is '{demo_status}', not 'active' — Frame A will show a refusal")

    affected = affected_set(events, HERO_USE_TYPE)
    print(f"\n{INFO}revoking '{HERO_USE_TYPE}' on {HERO_WORK} would affect "
          f"{len(affected)} grant(s):")
    uncached = 0
    for gid, cp, use_type in affected:
        cached = notice_is_cached(gid, HERO_WORK, cp)
        uncached += 0 if cached else 1
        label = "CACHED    (~0 ms)" if cached else "NOT CACHED (~4.7 s live Gemini call)"
        print(f"          {gid:22} {cp:24} {use_type:14} notice {label}")

    expected = 2 if args.two_counterparty else 1
    if len(affected) != expected:
        failures.append(f"affected set is {len(affected)}, expected {expected}")

    # Warm 1-grant base ~0.55 s (create-only runtime SA, measured 2026-08-10);
    # each uncached notice adds one ~4.7 s live Gemini call.
    predicted = "~0.5 s" if uncached == 0 else f"~{0.55 + 4.7 * uncached:.1f} s"
    print(f"\n{INFO}PREDICTED cascade round-trip: {predicted} "
          f"({len(affected)} affected, {uncached} uncached notice call(s))")
    print(f"{INFO}log depth for {HERO_WORK}: {len(events)} events "
          f"(append-only; grows two per take, which is expected and visible)")

    # ---- 5. the service -----------------------------------------------------
    if not args.between_takes:
        print("\n[5] deployed service")
        import time
        import urllib.request
        base = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app"
        try:
            t0 = time.perf_counter()
            code = urllib.request.urlopen(base + "/", timeout=90).getcode()
            ms = (time.perf_counter() - t0) * 1000
            print(f"{OK if code == 200 else BAD}GET / -> HTTP {code} in {ms:.0f} ms "
                  f"({'warm' if ms < 1500 else 'COLD — warm again just before rolling'})")
            if code != 200:
                failures.append(f"service returned HTTP {code}")
        except Exception as exc:
            failures.append(f"service unreachable: {exc}")
            print(f"{BAD}service unreachable: {exc}")

    # ---- verdict ------------------------------------------------------------
    print("\n" + "=" * 78)
    if failures:
        print("RECORDING STATE NOT READY:")
        for f in failures:
            print(f"  - {f}")
        print("=" * 78)
        return 1
    print(f"RECORDING STATE READY — cascade on the {predicted} path.")
    if not args.between_takes:
        print("Still yours: export the two secrets, run `make demo-live` for the 6/6, "
              "and warm the service before each take.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
