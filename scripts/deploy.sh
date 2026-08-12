#!/usr/bin/env bash
# scripts/deploy.sh — the ONE reproducible deployment path (`make deploy`).
#
# WHY THIS EXISTS. Deployment was a command in a memory note, and one flag in it
# is load-bearing: `--service-account hodi-runtime-sa@...`. Without it Cloud Run
# falls back to the DEFAULT COMPUTE service account, which holds roles/editor —
# i.e. datastore.entities.update and .delete. The service keeps working, every
# test keeps passing, and the append-only invariant the whole audit trail rests
# on becomes false at runtime with nothing failing loudly. That is precisely the
# defect shape this project exists to refuse, and a hand-typed command is not a
# mechanism.
#
# So this script does the whole thing and then PROVES the result:
#   1. provision IAM (idempotent) — the four policy SAs and the runtime SA
#   2. deploy from the repository-root Dockerfile with the runtime SA bound
#   3. read the deployed identity back and assert it cannot rewrite history
#
# It refuses to report success on step 2 alone.

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
REGION="${HODI_REGION:-us-central1}"
SERVICE="${HODI_SERVICE:-hodi-evidence-endpoint}"
RUNTIME_SA="hodi-runtime-sa@${PROJECT_ID}.iam.gserviceaccount.com"

cd "$(dirname "$0")/.."

echo "================================================================================"
echo "HODI DEPLOY — ${SERVICE} → ${REGION} (${PROJECT_ID})"
echo "  runtime identity: ${RUNTIME_SA}"
echo "================================================================================"

echo
echo "[1/3] Provisioning IAM (idempotent)..."
./scripts/deploy_gcp.sh

echo
echo "[2/3] Deploying from the repository-root Dockerfile..."
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${RUNTIME_SA}" \
  --quiet

echo
echo "[3/3] Verifying the DEPLOYED identity cannot rewrite grant history..."
DEPLOYED_SA="$(gcloud run services describe "${SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(spec.template.spec.serviceAccountName)')"
echo "  deployed as: ${DEPLOYED_SA}"

if [ "${DEPLOYED_SA}" != "${RUNTIME_SA}" ]; then
  echo "FAILED: service runs as '${DEPLOYED_SA}', not the create-only runtime SA." >&2
  echo "        Append-only is NOT enforced by IAM in this revision." >&2
  exit 1
fi

# The real assertion: expand every role the runtime identity holds and confirm
# the effective permission set can create but not update or delete.
HODI_E2E=1 GCP_PROJECT_ID="${PROJECT_ID}" HODI_SERVICE="${SERVICE}" HODI_REGION="${REGION}" \
  python3 -m unittest tests.test_grant_log_iam.TestDeployedRuntimeIdentityCannotRewriteHistory -v

echo
echo "================================================================================"
echo "DEPLOYED AND VERIFIED — ${SERVICE} runs as a create-only identity."
echo "Still yours: \`make demo-live\` for the 6/6 boundary check, and"
echo "\`make recording-prep\` if you are about to record."
echo "================================================================================"
