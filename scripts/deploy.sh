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

# Environment the service needs, assembled from what actually EXISTS — the
# deploy never claims a capability whose backing infrastructure is absent:
#   * HODI_SIGNING=kms + key version, only if the Cloud KMS key is reachable
#     (setup_kms_signing.sh); otherwise the service keeps labelled-ephemeral
#     signing, which is honest rather than broken.
#   * HODI_REVOCATION_WORKER_URL, only if the split worker service exists
#     (deploy_revocation_worker.sh); the registry then publishes a real
#     endpoint instead of the in-process placeholder.
KMS_KEY="${HODI_KMS_KEY:-hodi-provenance}"
KMS_KEYRING="${HODI_KMS_KEYRING:-hodi-signing}"
KMS_LOCATION="${HODI_KMS_LOCATION:-us-central1}"
ENV_VARS=""
if gcloud kms keys describe "${KMS_KEY}" --keyring "${KMS_KEYRING}" \
     --location "${KMS_LOCATION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  KMS_VERSION="projects/${PROJECT_ID}/locations/${KMS_LOCATION}/keyRings/${KMS_KEYRING}/cryptoKeys/${KMS_KEY}/cryptoKeyVersions/1"
  ENV_VARS="HODI_SIGNING=kms,HODI_KMS_KEY_VERSION=${KMS_VERSION}"
  echo "  signing: Cloud KMS (${KMS_KEY})"
else
  # SET the mode, do not merely announce it. This branch printed
  # "labelled-ephemeral signing" while setting nothing, and signing.py selects a
  # signer ONLY from an explicit HODI_SIGNING value — so a KMS-less deployment
  # announced one behaviour and shipped another (unsigned placeholders). A
  # deploy script that describes a capability it did not configure is the exact
  # code/deployment disagreement this repo exists to catch.
  ENV_VARS="HODI_SIGNING=ephemeral"
  echo "  signing: KMS key not found — configuring labelled-ephemeral signing"
fi
WORKER_URL="$(gcloud run services describe "${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "${WORKER_URL}" ]; then
  ENV_VARS="${ENV_VARS:+${ENV_VARS},}HODI_REVOCATION_WORKER_URL=${WORKER_URL}"
  echo "  revocation worker endpoint: ${WORKER_URL}"
else
  echo "  revocation worker: not deployed — registry keeps the in-process placeholder"
fi

gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${RUNTIME_SA}" \
  ${ENV_VARS:+--update-env-vars "${ENV_VARS}"} \
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

# When KMS signing is enabled, the public verification key must be served —
# a signature nobody can fetch the key for is decoration, not provenance.
if [ -n "${ENV_VARS}" ] && printf '%s' "${ENV_VARS}" | grep -q 'HODI_SIGNING=kms'; then
  SERVICE_URL="$(gcloud run services describe "${SERVICE}" \
    --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
  VK_BODY="$(curl -s --max-time 90 "${SERVICE_URL}/verification-key" || true)"
  printf '%s' "${VK_BODY}" | grep -q "BEGIN PUBLIC KEY" \
    || { echo "FAIL: /verification-key does not serve the public key"; exit 1; }
  echo "  /verification-key serves the KMS public key"
fi

# The revocation worker is a SEPARATE service that `make deploy` does not build.
# On 2026-08-14 it silently ran 85 minutes behind HEAD — same repository, stale
# image, nothing failing — carrying the pre-fix SA literals and the fail-open
# storage path. A deploy that leaves a sibling service on older code should say
# so rather than let the operator assume one coherent release.
WORKER_SERVICE="${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}"
WORKER_REV_CREATED="$(gcloud run revisions describe \
  "$(gcloud run services describe "${WORKER_SERVICE}" --region "${REGION}" \
       --project "${PROJECT_ID}" --format='value(status.latestReadyRevisionName)' 2>/dev/null)" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(metadata.creationTimestamp)' 2>/dev/null || true)"
if [ -n "${WORKER_REV_CREATED}" ]; then
  HEAD_EPOCH="$(git -C "$(dirname "$0")/.." log -1 --format=%ct)"
  WORKER_EPOCH="$(date -j -f '%Y-%m-%dT%H:%M:%S' "${WORKER_REV_CREATED%%.*}" +%s 2>/dev/null \
                  || date -d "${WORKER_REV_CREATED}" +%s 2>/dev/null || echo 0)"
  if [ "${WORKER_EPOCH}" -lt "${HEAD_EPOCH}" ] 2>/dev/null; then
    echo
    echo "WARNING: ${WORKER_SERVICE} was built BEFORE the current HEAD commit."
    echo "         It is running older code from this same repository."
    echo "         Redeploy it:  ./scripts/deploy_revocation_worker.sh"
  else
    echo "  revocation worker: build postdates HEAD (coherent release)"
  fi
else
  echo "  revocation worker: not deployed"
fi

echo
echo "================================================================================"
echo "DEPLOYED AND VERIFIED — ${SERVICE} runs as a create-only identity."
echo "Still yours: \`make demo-live\` for the 6/6 boundary check, and"
echo "\`make recording-prep\` if you are about to record."
echo "================================================================================"
