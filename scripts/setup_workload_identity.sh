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
# STATUS: designed and scripted; NOT executed against the live project in the
# 2026-08-14 session (BUILD-LOG). Row-level scoping (counterparty_id) remains
# gateway-enforced and is unaffected — this hardens the DOMAIN boundary, which
# is the one the review asked to make real.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
LOCATION="${HODI_FIRESTORE_LOCATION:-nam5}"

echo "== Hodi workload-identity separation — project ${PROJECT_ID} =="

# 1. The named databases, one per conflict domain, from the policy module.
mapfile -t ROWS < <(python3 - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
from src.schema.iam_policy import AGENT_SA_MAP, CONFLICT_DOMAIN_DATABASE
seen = set()
for role, info in AGENT_SA_MAP.items():
    db = CONFLICT_DOMAIN_DATABASE.get(info["conflict_domain"], "(default)")
    sa = info["sa_email"]
    print(f"{role}\t{info['conflict_domain']}\t{db}\t{sa}")
PY
)

declare -A DB_SEEN
for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r role domain db sa <<<"${row}"
  if [ "${db}" != "(default)" ] && [ -z "${DB_SEEN[$db]:-}" ]; then
    DB_SEEN[$db]=1
    if ! gcloud firestore databases describe --database="${db}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
      echo "[db] creating ${db} (domain: ${domain})"
      gcloud firestore databases create --database="${db}" \
        --location="${LOCATION}" --type=firestore-native --project="${PROJECT_ID}"
    else
      echo "[db] ${db} exists"
    fi
  fi
done

# 2. Per-database IAM: each agent SA gets datastore access ONLY on its domain's
#    database, via an IAM condition on the database resource name. A foreign
#    database is therefore uncredentialed for that SA.
for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r role domain db sa <<<"${row}"
  [ "${db}" = "(default)" ] && { echo "[iam] ${role}: (default) db — covered by the append-only role"; continue; }
  echo "[iam] ${role} (${sa}) → datastore.viewer on database '${db}' ONLY"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${sa}" \
    --role="roles/datastore.viewer" \
    --condition="expression=resource.name.endsWith('/databases/${db}'),title=only-${db}" \
    --quiet >/dev/null
done

echo
echo "== PROOF (run after provisioning) =="
echo "  HODI_E2E=1 python3 -m unittest tests.test_workload_identity -v"
echo "  # asserts a foreign-domain read is PERMISSION_DENIED by IAM, not by the app."
echo
echo "NOTE: the deployed service must set HODI_DB_ROUTING=1 and run each split"
echo "workload under its domain SA for these bindings to take effect. The single-"
echo "process deployment continues to enforce the same boundary in-application."
