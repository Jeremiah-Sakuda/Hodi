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
# WHAT THE FIRST VERSION GOT WRONG, kept here because both mistakes are this
# repo's recurring classes:
#   * It deployed a worker that could not run. The propagator SA held ONLY the
#     append-only custom role (create/get/list) — no datastore.databases.get —
#     so every Firestore read 500'd. This is the exact failure the runtime SA
#     hit on 2026-08-10. A deploy script that does not provision what the
#     workload needs is infrastructure-reported-done.
#   * It set HODI_ROLE and HODI_DB_ROUTING, and NOTHING CONSUMES EITHER — two
#     dead env vars dressing the deploy up as more separated than it is. The
#     revocation domain's database is (default) (src/schema/iam_policy.py:
#     CONFLICT_DOMAIN_DATABASE), which is where the grant log actually lives,
#     so no routing flag is needed for this worker to be correctly scoped.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
REGION="${HODI_REGION:-us-central1}"
WORKER_SERVICE="${HODI_REVOCATION_SERVICE:-hodi-revocation-worker}"
PROPAGATOR_SA="revocation-propagator-sa@${PROJECT_ID}.iam.gserviceaccount.com"
FRONT_DOOR_SA="hodi-runtime-sa@${PROJECT_ID}.iam.gserviceaccount.com"

cd "$(dirname "$0")/.."

echo "== Deploying the revocation worker as its own service =="
echo "  service:  ${WORKER_SERVICE}"
echo "  identity: ${PROPAGATOR_SA} (revocation domain only)"

# 1. Provision what the workload NEEDS, before deploying it. Database roles are
#    conditioned to `(default)`, where the grant log and revocation outbox live.
#    A project-wide viewer or append role would also reach every named conflict
#    database and collapse the boundary despite the distinct service account.
#      - aiplatform.user: Gemini notice drafting
#      - logging.logWriter: structured logs
for role in "roles/datastore.viewer" "projects/${PROJECT_ID}/roles/hodiAppendOnlyGrantWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROPAGATOR_SA}" \
    --role="${role}" \
    --condition="expression=resource.name.endsWith('/databases/(default)'),title=revocation-default-only" \
    --quiet >/dev/null
  echo "  [iam] bound ${role}, conditioned to (default)"
  if gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${PROPAGATOR_SA}" --role="${role}" \
      --condition=None --quiet >/dev/null 2>&1; then
    echo "        removed prior unconditional binding"
  else
    echo "        no prior unconditional binding present"
  fi
done
for role in "roles/aiplatform.user" "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROPAGATOR_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
  echo "  [iam] bound non-data role ${role}"
done

# Moving execution must not regress verified notices to placeholders. Configure
# the worker for the same asymmetric key when it exists; otherwise select the
# explicit labelled-ephemeral mode.
KMS_KEY="${HODI_KMS_KEY:-hodi-provenance}"
KMS_KEYRING="${HODI_KMS_KEYRING:-hodi-signing}"
KMS_LOCATION="${HODI_KMS_LOCATION:-us-central1}"
WORKER_ENV="GCP_PROJECT_ID=${PROJECT_ID},HODI_SERVICE_ROLE=revocation_propagator,HODI_FRONT_DOOR_SA=${FRONT_DOOR_SA}"
if gcloud kms keys describe "${KMS_KEY}" --keyring "${KMS_KEYRING}" \
    --location "${KMS_LOCATION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud kms keys add-iam-policy-binding "${KMS_KEY}" \
    --keyring "${KMS_KEYRING}" --location "${KMS_LOCATION}" --project "${PROJECT_ID}" \
    --member="serviceAccount:${PROPAGATOR_SA}" --role="roles/cloudkms.signer" \
    --quiet >/dev/null
  KMS_VERSION="projects/${PROJECT_ID}/locations/${KMS_LOCATION}/keyRings/${KMS_KEYRING}/cryptoKeys/${KMS_KEY}/cryptoKeyVersions/1"
  WORKER_ENV="${WORKER_ENV},HODI_SIGNING=kms,HODI_KMS_KEY_VERSION=${KMS_VERSION}"
  echo "  [iam] KMS signer bound on ${KMS_KEY}; worker configured for KMS signing"
else
  WORKER_ENV="${WORKER_ENV},HODI_SIGNING=ephemeral"
  echo "  [iam] KMS key absent; worker configured for labelled-ephemeral signing"
fi

# 2. Deploy from the repository-root Dockerfile, private by default: only
#    identities holding run.invoker (the supervisor / operator) can call it.
gcloud run deploy "${WORKER_SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${PROPAGATOR_SA}" \
  --no-allow-unauthenticated \
  --set-env-vars "${WORKER_ENV}" \
  --quiet

WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"

gcloud run services add-iam-policy-binding "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --member="serviceAccount:${FRONT_DOOR_SA}" --role="roles/run.invoker" \
  --quiet >/dev/null

echo
echo "== PROOF, not report =="

# 3a. The deployed identity is the propagator SA, not the shared runtime SA.
DEPLOYED_SA="$(gcloud run services describe "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(spec.template.spec.serviceAccountName)')"
[ "${DEPLOYED_SA}" = "${PROPAGATOR_SA}" ] \
  || { echo "FAIL: worker runs as '${DEPLOYED_SA}', not the propagator SA"; exit 1; }
echo "  worker identity verified: ${DEPLOYED_SA}"

# 3b. The worker's effective permissions cannot rewrite history: expand every
#     role the propagator SA holds and assert create present, update/delete absent.
# (if/else, not `case`: bash 3.2 cannot parse case patterns inside $(...).)
EFFECTIVE="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten='bindings[].members' --format='value(bindings.role)' \
  --filter="bindings.members:${PROPAGATOR_SA}" | sort -u | while IFS= read -r role; do
    if [ "${role#projects/}" != "${role}" ]; then
      gcloud iam roles describe "${role##*/}" --project="${PROJECT_ID}" --format='value(includedPermissions)'
    else
      gcloud iam roles describe "${role}" --format='value(includedPermissions)'
    fi
  done | tr ';' '\n' | sort -u)"
echo "${EFFECTIVE}" | grep -q '^datastore.entities.create$' \
  || { echo "FAIL: propagator SA cannot append grant events"; exit 1; }
for forbidden in datastore.entities.update datastore.entities.delete; do
  if echo "${EFFECTIVE}" | grep -q "^${forbidden}$"; then
    echo "FAIL: propagator SA holds ${forbidden} — grant history is rewritable from the worker"
    exit 1
  fi
done
echo "  effective permissions verified: append + read, no update, no delete"

# A conditioned grant beside a broad one narrows nothing. Prove that neither
# data role remains unconditioned on the propagator identity.
UNCONDITIONED="$(gcloud projects get-iam-policy "${PROJECT_ID}" --format=json \
  | python3 -c "
import json,sys
p=json.load(sys.stdin); me='serviceAccount:${PROPAGATOR_SA}'
bad=[b['role'] for b in p['bindings']
     if me in b.get('members',[]) and not b.get('condition')
     and ('datastore' in b['role'] or 'GrantWriter' in b['role'])]
print(','.join(bad))
")"
[ -z "${UNCONDITIONED}" ] \
  || { echo "FAIL: propagator still holds unconditioned database grants: ${UNCONDITIONED}"; exit 1; }
echo "  database scope verified: (default) only"

# 3c. The worker answers an AUTHENTICATED request and refuses an anonymous one.
AUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 120 \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${WORKER_URL}/")"
ANON_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "${WORKER_URL}/")"
[ "${AUTH_CODE}" = "200" ] \
  || { echo "FAIL: authenticated request to the worker returned HTTP ${AUTH_CODE}"; exit 1; }
case "${ANON_CODE}" in
  401|403) : ;;
  *) echo "FAIL: anonymous request returned HTTP ${ANON_CODE} — the worker is public"; exit 1 ;;
esac
echo "  invocation verified: authenticated 200, anonymous ${ANON_CODE}"
echo "  worker URL: ${WORKER_URL}"

echo
echo "== Wiring =="
echo "The registry publishes the worker's endpoint when the MAIN service carries:"
echo "  HODI_REVOCATION_WORKER_URL=${WORKER_URL}"
echo "(consumed by src/fleet/adk_fleet.py — set it via scripts/deploy.sh or:"
echo "  gcloud run services update hodi-evidence-endpoint --region ${REGION} \\"
echo "    --update-env-vars HODI_REVOCATION_WORKER_URL=${WORKER_URL})"
