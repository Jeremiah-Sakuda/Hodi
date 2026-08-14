#!/usr/bin/env bash
# scripts/deploy_revocation_worker.sh — split the revocation worker into its
# OWN Cloud Run service under its OWN service account (HOD-711, HOD-707).
#
# Two things become real at once:
#   * WORKLOAD IDENTITY — the revocation worker executes as the revocation-
#     propagator SA, not the shared runtime SA, so its credentials are exactly
#     the revocation domain's and nothing else. The conflict boundary is a
#     credential boundary for this agent.
#   * KILLABLE ISOLATION — a separate Cloud Run service is a process the
#     supervisor can actually terminate (Cloud Run request timeout / instance
#     recycle), which is the hard-termination story the in-process daemon
#     thread cannot provide. Execution leases (HOD-707) remain the safety
#     property that holds REGARDLESS of whether the thread stops.
#
# STATUS: designed and scripted; NOT executed against the live project in the
# 2026-08-14 session (BUILD-LOG). The single-process deployment keeps running
# the cascade in-process under application-layer separation until this runs.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
REGION="${HODI_REGION:-us-central1}"
WORKER_SERVICE="${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}"
PROPAGATOR_SA="revocation-propagator-sa@${PROJECT_ID}.iam.gserviceaccount.com"

cd "$(dirname "$0")/.."

echo "== Deploying the revocation worker as its own service =="
echo "  service:  ${WORKER_SERVICE}"
echo "  identity: ${PROPAGATOR_SA} (revocation domain only)"

# The propagator SA needs append+read on the grant log (the custom role) and
# aiplatform.user for notice drafting — and NOTHING on the identity, commercial
# or evidence databases. deploy_gcp.sh already binds the append-only role to it.
gcloud run deploy "${WORKER_SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${PROPAGATOR_SA}" \
  --set-env-vars "HODI_ROLE=revocation_propagator,HODI_DB_ROUTING=1" \
  --no-allow-unauthenticated \
  --quiet

WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"

echo
echo "== PROOF, not report =="
DEPLOYED_SA="$(gcloud run services describe "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(spec.template.spec.serviceAccountName)')"
[ "${DEPLOYED_SA}" = "${PROPAGATOR_SA}" ] \
  || { echo "FAIL: worker runs as '${DEPLOYED_SA}', not the propagator SA"; exit 1; }
echo "  worker identity verified: ${DEPLOYED_SA}"
echo "  worker URL: ${WORKER_URL}"
echo
echo "Register the worker's endpoint so discovery returns a real URL:"
echo "  export HODI_REVOCATION_WORKER_URL=${WORKER_URL}"
echo "Then the main service's registry publishes it (src/fleet/adk_fleet.py)."
echo
echo "Prove the identity separation is a CREDENTIAL boundary:"
echo "  HODI_E2E=1 python3 -m unittest tests.test_workload_identity -v"
