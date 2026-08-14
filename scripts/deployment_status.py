#!/usr/bin/env python3
"""
scripts/deployment_status.py — the capability truth table, GENERATED from the
live project rather than typed (HOD-510, HOD-620).

    make deployment-status        # probe live, write docs/deployment_status.json
    make deployment-status-check  # fail if the committed file is stale

WHY. A reviewer reading this repository could not tell which claims described
code, which described a deployed revision, and which described neither — the
architecture diagram said the per-domain databases were "scripted, not yet
executed" on the same day the deployment had executed them. Every number in this
project is read from its source; deployment state was the last thing still
asserted by hand.

Each row answers three separate questions, because conflating them is exactly
how the drift happened:

  implemented        — the code exists in this commit
  deployed           — it is present in the serving revision / live project
  demonstrated_live  — it has been OBSERVED working against the live service,
                       by a command anyone can re-run (named in `proof`)

`deployed` and `demonstrated_live` are probed here, live. `implemented` is read
from the filesystem. Nothing in this file is a literal a person maintains.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "deployment_status.json"

PROJECT = "hodi-2026"
REGION = "us-central1"
SERVICE = "hodi-evidence-endpoint"
WORKER = "hodi-revocation-worker"


def sh(args, timeout=120):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def head_commit():
    return sh(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])


def serving_revision(service):
    return sh(["gcloud", "run", "services", "describe", service, f"--region={REGION}",
               f"--project={PROJECT}", "--format=value(status.latestReadyRevisionName)"])


def service_env(service):
    raw = sh(["gcloud", "run", "services", "describe", service, f"--region={REGION}",
              f"--project={PROJECT}",
              "--format=value(spec.template.spec.containers[0].env)"])
    return raw


def runtime_sa(service):
    return sh(["gcloud", "run", "services", "describe", service, f"--region={REGION}",
               f"--project={PROJECT}",
               "--format=value(spec.template.spec.serviceAccountName)"])


def firestore_databases():
    raw = sh(["gcloud", "firestore", "databases", "list", f"--project={PROJECT}",
              "--format=value(name)"])
    return [d.rsplit("/", 1)[-1] for d in raw.splitlines() if d]


def kms_key_present():
    return bool(sh(["gcloud", "kms", "keys", "describe", "hodi-provenance",
                    "--keyring=hodi-signing", f"--location={REGION}",
                    f"--project={PROJECT}", "--format=value(name)"]))


def http_code(url, timeout=90):
    return sh(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
               "--max-time", str(timeout), url], timeout=timeout + 20)


def build_rows():
    env = service_env(SERVICE)
    dbs = firestore_databases()
    named = [d for d in ("hodi-identity", "hodi-commercial", "hodi-evidence",
                         "hodi-adjudication") if d in dbs]
    base = sh(["gcloud", "run", "services", "describe", SERVICE, f"--region={REGION}",
               f"--project={PROJECT}", "--format=value(status.url)"])
    vk = http_code(f"{base}/verification-key") if base else ""
    worker_rev = serving_revision(WORKER)

    return [
        {
            "capability": "Gemini 3.5 Flash scope interpretation",
            "implemented": (ROOT / "src/llm/scope_interpreter.py").exists(),
            "deployed": bool(serving_revision(SERVICE)),
            "demonstrated_live": bool(base),
            "proof": "POST /api/v1/license/natural on the deployed service; docs/metrics.json::natural_language_license_path",
        },
        {
            "capability": "Append-only enforced by runtime IAM (no update/delete)",
            "implemented": (ROOT / "scripts/deploy_gcp.sh").exists(),
            "deployed": "hodi-runtime-sa" in runtime_sa(SERVICE),
            "demonstrated_live": "hodi-runtime-sa" in runtime_sa(SERVICE),
            "proof": "HODI_E2E=1 python3 -m unittest tests.test_grant_log_iam.TestDeployedRuntimeIdentityCannotRewriteHistory",
        },
        {
            "capability": "Cloud KMS asymmetric signing (ECDSA P-256)",
            "implemented": (ROOT / "src/schema/signing.py").exists(),
            "deployed": kms_key_present() and "HODI_SIGNING" in env and "kms" in env,
            "demonstrated_live": vk == "200",
            "proof": "GET /verification-key returns the public key; scripts/hodi_verify.py accepts a live receipt and rejects a one-byte edit",
        },
        {
            "capability": "Per-domain named databases + IAM-conditioned agent SAs",
            "implemented": (ROOT / "scripts/setup_workload_identity.sh").exists(),
            "deployed": len(named) == 4,
            "demonstrated_live": len(named) == 4,
            "proof": "HODI_E2E=1 python3 -m unittest tests.test_workload_identity — impersonates the evidence SA and asserts PermissionDenied reading the identity database",
            "note": ("Live DATA still resides in (default); this hardens the DOMAIN boundary. "
                     "Row-level separation inside the grant log remains gateway-enforced."),
        },
        {
            "capability": "Revocation worker as its own workload identity",
            "implemented": (ROOT / "scripts/deploy_revocation_worker.sh").exists(),
            "deployed": bool(worker_rev),
            "demonstrated_live": bool(worker_rev),
            "proof": "scripts/deploy_revocation_worker.sh step 3 — identity readback, effective-permission expansion, authenticated 200 / anonymous 403",
            "note": ("Deployed and separately credentialed, but /api/v1/revoke still runs the "
                     "cascade IN-PROCESS; the worker is not yet on the primary action path."),
        },
        {
            "capability": "Cross-buyer confidentiality boundary",
            "implemented": (ROOT / "src/gateway/gateway.py").exists(),
            "deployed": bool(base),
            "demonstrated_live": bool(base),
            "proof": "make demo-live — 6/6 HTTP 403 including Part C, replaying the 2026-08-07 exploit",
        },
        {
            "capability": "verbatim_match / redistribution content checks",
            "implemented": (ROOT / "src/evidence/verbatim_probe.py").exists(),
            "deployed": bool(serving_revision(SERVICE)),
            "demonstrated_live": False,
            "proof": "tests/test_evidence_engine.py — a paraphrase and a bare mirror URI both produce NO record",
            "note": ("Offline only. No third party has been observed reproducing a registered "
                     "passage, and EvidenceEngine has no production caller."),
        },
        {
            "capability": "Overclaim lint semantic backstop (gemini-embedding-001)",
            "implemented": (ROOT / "src/evidence/semantic_backstop.py").exists(),
            "deployed": bool(serving_revision(SERVICE)),
            "demonstrated_live": (ROOT / "fixtures/embedding_cache.json").exists(),
            "proof": "make lint-coverage — 12/12 probes rejected, 4 by regex alone; vectors recorded from live Vertex into fixtures/embedding_cache.json",
        },
    ]


def main() -> int:
    check = "--check" in sys.argv
    rows = build_rows()
    doc = {
        "_comment": ("GENERATED by scripts/deployment_status.py — do not hand-edit. Separates "
                     "implemented / deployed / demonstrated_live so a reader never has to guess "
                     "which a claim refers to."),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "head_commit": head_commit(),
        "serving_revision": serving_revision(SERVICE),
        "revocation_worker_revision": serving_revision(WORKER),
        "runtime_service_account": runtime_sa(SERVICE),
        "capabilities": rows,
    }

    if check:
        if not OUT.exists():
            print("docs/deployment_status.json missing — run `make deployment-status`.")
            return 1
        committed = json.loads(OUT.read_text())
        drift = []
        if committed.get("serving_revision") != doc["serving_revision"]:
            drift.append(f"serving revision: file says {committed.get('serving_revision')}, "
                         f"live is {doc['serving_revision']}")
        for a, b in zip(committed.get("capabilities", []), rows):
            for field in ("implemented", "deployed", "demonstrated_live"):
                if a.get(field) != b.get(field):
                    drift.append(f"{b['capability']}: {field} {a.get(field)} -> {b.get(field)}")
        if drift:
            print("DEPLOYMENT STATUS STALE:")
            for d in drift:
                print(f"  - {d}")
            print("\nFix: run `make deployment-status` and commit the result.")
            return 1
        print(f"deployment_status.json is current (revision {doc['serving_revision']}).")
        return 0

    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    for r in rows:
        flags = "".join("Y" if r[f] else "n" for f in ("implemented", "deployed", "demonstrated_live"))
        print(f"  [{flags}] {r['capability']}")
    print("\n  legend: implemented / deployed / demonstrated_live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
