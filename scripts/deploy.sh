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
echo "  deploying the required private revocation workload from this source tree"
./scripts/deploy_revocation_worker.sh
WORKER_URL="$(gcloud run services describe "${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
ENV_VARS="${ENV_VARS:+${ENV_VARS},}HODI_REVOCATION_WORKER_URL=${WORKER_URL}"
echo "  revocation execution: private worker ${WORKER_URL} (required; no live in-process fallback)"

# Domain services, DISCOVERED from Cloud Run rather than read from a local file.
# All four are required: silently omitting this variable would re-enable the
# in-process path and collapse the deployed conflict boundary.
DOMAIN_URLS=""
for role in rights_custodian licensing_negotiator evidence_agent consent_arbiter; do
  svc="hodi-$(echo "${role}" | tr '_' '-')"
  if ! url="$(gcloud run services describe "${svc}" --region "${REGION}" \
      --project "${PROJECT_ID}" --format='value(status.url)' 2>/dev/null)" \
      || [ -z "${url}" ]; then
    echo "FAIL: required conflict-domain service '${svc}' is unavailable." >&2
    echo "      Run ./scripts/deploy_domain_services.sh before deploying the front door." >&2
    exit 1
  fi
  DOMAIN_URLS="${DOMAIN_URLS:+${DOMAIN_URLS}|}${role}=${url}"
done
ENV_VARS="${ENV_VARS:+${ENV_VARS},}HODI_DOMAIN_SERVICE_URLS=${DOMAIN_URLS}"
echo "  domain services: delegating to $(( $(echo "${DOMAIN_URLS}" | tr -cd '|' | wc -c) + 1 )) required workloads"

# Durable trace backend, set only if BOTH halves of it actually exist: the API
# enabled, and the runtime identity holding roles/cloudtrace.agent. Setting
# HODI_TRACE_EXPORT=cloud without those makes the exporter fail to build and the
# service fall back to the console — spans still print, nothing durable is
# written, and the deployment looks healthy the whole time. That fallback is now
# loud (src/observability/tracing.py), but the deploy should not create the
# condition in the first place.
if gcloud services list --enabled --project "${PROJECT_ID}" --format='value(config.name)' 2>/dev/null \
     | grep -qx "cloudtrace.googleapis.com" \
   && gcloud projects get-iam-policy "${PROJECT_ID}" --flatten='bindings[].members' \
        --filter="bindings.members:serviceAccount:${RUNTIME_SA} AND bindings.role:roles/cloudtrace.agent" \
        --format='value(bindings.role)' 2>/dev/null | grep -q .; then
  ENV_VARS="${ENV_VARS:+${ENV_VARS},}HODI_TRACE_EXPORT=cloud"
  echo "  traces: Cloud Trace (API enabled, runtime identity holds cloudtrace.agent)"
else
  echo "  traces: console only — cloudtrace API or roles/cloudtrace.agent missing"
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
  if ! VK_BODY="$(curl -s --fail --max-time 90 "${SERVICE_URL}/verification-key")"; then
    echo "FAIL: /verification-key could not be fetched" >&2
    exit 1
  fi
  printf '%s' "${VK_BODY}" | grep -q "BEGIN PUBLIC KEY" \
    || { echo "FAIL: /verification-key does not serve the public key"; exit 1; }
  echo "  /verification-key serves the KMS public key"
fi

# The revocation worker is a separate service. `make deploy` rebuilds it from
# the same source tree and refuses to omit its URL; this freshness proof catches
# a worker revision that did not actually advance.
WORKER_SERVICE="${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}"
WORKER_REV="$(gcloud run services describe "${WORKER_SERVICE}" --region "${REGION}" \
  --project "${PROJECT_ID}" --format='value(status.latestReadyRevisionName)')"
WORKER_REV_CREATED="$(gcloud run revisions describe "${WORKER_REV}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(metadata.creationTimestamp)')"
HEAD_EPOCH="$(git -C "$(dirname "$0")/.." log -1 --format=%ct)"
if WORKER_EPOCH="$(date -j -u -f '%Y-%m-%dT%H:%M:%S' "${WORKER_REV_CREATED%%.*}" +%s 2>/dev/null)"; then
  :
elif WORKER_EPOCH="$(date -u -d "${WORKER_REV_CREATED}" +%s 2>/dev/null)"; then
  :
else
  echo "FAIL: could not parse worker revision timestamp '${WORKER_REV_CREATED}'" >&2
  exit 1
fi
if [ "${WORKER_EPOCH}" -lt "${HEAD_EPOCH}" ]; then
  echo "FAIL: ${WORKER_SERVICE} was built before the current HEAD commit." >&2
  echo "      Redeploy it with ./scripts/deploy_revocation_worker.sh." >&2
  exit 1
fi
echo "  revocation worker: build postdates HEAD (coherent release)"

echo
echo "================================================================================"
echo "DEPLOYED AND VERIFIED — ${SERVICE} runs as a create-only identity."
echo "Still yours: \`make demo-live\` for the 6/6 boundary check, and"
echo "\`make recording-prep\` if you are about to record."
echo "================================================================================"
