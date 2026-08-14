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

cd "$(dirname "$0")/.."

echo "== Deploying the revocation worker as its own service =="
echo "  service:  ${WORKER_SERVICE}"
echo "  identity: ${PROPAGATOR_SA} (revocation domain only)"

# 1. Provision what the workload NEEDS, before deploying it. Same recipe that
#    made the runtime SA viable, none of it grants update or delete:
#      - the append-only custom role: already bound by deploy_gcp.sh (create/get/list)
#      - datastore.viewer: all Firestore READ permissions incl. databases.get, zero writes
#      - aiplatform.user: Gemini notice drafting
#      - logging.logWriter: structured logs
for role in "roles/datastore.viewer" "roles/aiplatform.user" "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROPAGATOR_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
  echo "  [iam] bound ${role}"
done

# 2. Deploy from the repository-root Dockerfile, private by default: only
#    identities holding run.invoker (the supervisor / operator) can call it.
gcloud run deploy "${WORKER_SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${PROPAGATOR_SA}" \
  --no-allow-unauthenticated \
  --quiet

WORKER_URL="$(gcloud run services describe "${WORKER_SERVICE}" \
  --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"

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
