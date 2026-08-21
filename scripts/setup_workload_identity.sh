#!/usr/bin/env bash
# scripts/setup_workload_identity.sh — make the conflict boundary a CREDENTIAL
# boundary, not just an application one (HOD-711).
#
# WHAT THIS CHANGES. Today the four agent SAs are the identities the in-process
# policy layer names and audits, but the deployed service is ONE Cloud Run
# process under one runtime SA — so the conflict-of-interest separation is
# application-layer. This script provisions NAMED FIRESTORE DATABASES, one per
# conflict domain, and grants each agent SA datastore access ONLY on its own
# domain's database. After it, a workload holding the evidence SA that tries to
# read the identity database is refused by Google IAM, before any application
# code runs.
#
# The database map is GENERATED from src/schema/iam_policy.py
# (CONFLICT_DOMAIN_DATABASE), the same module the gateway and the conflict
# matrix read, so it cannot drift.
#
# PORTABILITY: written for bash 3.2 (macOS ships 3.2.57 — the first version of
# this script used `mapfile` and `declare -A`, both bash 4+, and could not run
# on the operator's machine at all). The row list is generated to a temp file
# and consumed with a plain read loop; database dedup is `cut | sort -u`.
#
# Named-database creation is effectively PERMANENT (deletion is gated and
# slow) and the new databases start EMPTY — live data stays in (default).
# Nothing here touches (default) or the running service; row-level scoping
# (counterparty_id) remains gateway-enforced and unaffected. This hardens the
# DOMAIN boundary, which is the one the review asked to make real.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
LOCATION="${HODI_FIRESTORE_LOCATION:-nam5}"

cd "$(dirname "$0")/.."

echo "== Hodi workload-identity separation — project ${PROJECT_ID} =="

gcloud services enable firestore.googleapis.com iamcredentials.googleapis.com \
  --project "${PROJECT_ID}"

# 1. The role → domain → database → SA rows, from the policy module. One tab-
#    separated row per agent; a temp file instead of mapfile (bash 3.2).
ROWS_FILE="$(mktemp)"
trap 'rm -f "${ROWS_FILE}"' EXIT
python3 - <<'PY' > "${ROWS_FILE}"
import os, sys
sys.path.insert(0, os.getcwd())
from src.schema.iam_policy import AGENT_SA_MAP, CONFLICT_DOMAIN_DATABASE
for role, info in AGENT_SA_MAP.items():
    db = CONFLICT_DOMAIN_DATABASE.get(info["conflict_domain"], "(default)")
    print(f"{role}\t{info['conflict_domain']}\t{db}\t{info['sa_email']}")
PY

echo "-- generated domain map --"
column -t -s $'\t' "${ROWS_FILE}" 2>/dev/null || cat "${ROWS_FILE}"

# 2. Create each named database once (dedup without associative arrays).
cut -f3 "${ROWS_FILE}" | sort -u | while IFS= read -r db; do
  [ "${db}" = "(default)" ] && continue
  if gcloud firestore databases describe --database="${db}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "[db] ${db} exists"
  else
    echo "[db] creating ${db}"
    gcloud firestore databases create --database="${db}" \
      --location="${LOCATION}" --type=firestore-native --project="${PROJECT_ID}"
  fi
done

# 3. Per-database IAM. Two moves per agent SA, and the SECOND is the one that
#    makes the boundary real:
#
#    (a) grant datastore.viewer conditioned to the SA's own domain database;
#    (b) REPLACE the SA's unconditional append-only binding with one conditioned
#        to (default) — the grant log's database, its only legitimate append
#        target.
#
#    (b) exists because the first execution of this script FAILED its own E2E
#    proof: the evidence SA read the identity database anyway. Cause: the
#    append-only custom role was bound WITHOUT a condition (deploy_gcp.sh), so
#    its datastore.entities.get applied to every database in the project, and
#    the conditional viewer merely added reads on top. Conditions narrow
#    nothing unless the broad grant is removed.
#
#    The revocation domain maps to (default), but it is NOT skipped. An
#    unconditional grant on that SA would span every named database as well;
#    default-only access must be expressed by an IAM condition just like every
#    other domain. The runtime SA is narrowed separately by the domain deploy.
while IFS=$'\t' read -r role domain db sa; do
  echo "[iam] ${role} (${sa}) -> viewer on '${db}' ONLY; append-only on (default) ONLY"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${sa}" \
    --role="roles/datastore.viewer" \
    --condition="expression=resource.name.endsWith('/databases/${db}'),title=only-${db}" \
    --quiet >/dev/null
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${sa}" \
    --role="projects/${PROJECT_ID}/roles/hodiAppendOnlyGrantWriter" \
    --condition="expression=resource.name.endsWith('/databases/(default)'),title=grant-log-only" \
    --quiet >/dev/null
  # Remove the unconditional binding LAST, so the SA is never left grantless.
  if gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${sa}" \
      --role="projects/${PROJECT_ID}/roles/hodiAppendOnlyGrantWriter" \
      --condition=None --quiet >/dev/null 2>&1; then
    echo "       removed unconditional append-only binding"
  else
    echo "       no unconditional append-only binding to remove"
  fi

  # The first worker deploy added an unconditional viewer to make Firestore
  # reads succeed. Remove that broad grant after the database-scoped one is in
  # place; otherwise this SA can still read every conflict database.
  if gcloud projects remove-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${sa}" --role="roles/datastore.viewer" \
      --condition=None --quiet >/dev/null 2>&1; then
    echo "       removed unconditional datastore.viewer binding"
  else
    echo "       no unconditional datastore.viewer binding to remove"
  fi
done < "${ROWS_FILE}"

echo
echo "== PROOF, not report =="
echo "The claim is 'a foreign-domain read is refused BY GOOGLE IAM'. That can"
echo "only be proven by attempting one with the foreign SA's own credentials:"
echo "  HODI_E2E=1 python3 -m unittest tests.test_workload_identity -v"
echo "(Impersonation requires roles/iam.serviceAccountTokenCreator for the"
echo " operator on the target SA; the test names the exact failure otherwise.)"
