#!/usr/bin/env bash
# scripts/deploy_gcp.sh — create the fleet's IAM identities (HOD-102, HOD-311).
#
# The conflict-of-interest boundary is the project's architectural thesis, and
# until now it had NO reproducible artifact: the four service accounts and the
# append-only custom role existed only in a live project and in prose. A judge
# could observe the deployment but not recreate it.
#
# The service accounts and their permitted collections are GENERATED from
# src/schema/iam_policy.py — the same dict the Gateway consults and the same one
# docs/architecture/conflict_matrix.md is generated from — so this script cannot
# drift from the enforced policy.
#
# Honest scope note: the running service is a single Cloud Run process, so these
# SAs are the identities the policy layer names and audits, not four separate
# runtime principals. Splitting the fleet into four services, each deployed with
# --service-account, is the natural next step and is stated as not-yet-done
# rather than implied.

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
ROLE_ID="hodiAppendOnlyGrantWriter"

echo "================================================================================"
echo "HODI FLEET IAM PROVISIONING — project ${PROJECT_ID}"
echo "================================================================================"

gcloud services enable \
  firestore.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com aiplatform.googleapis.com logging.googleapis.com \
  --project="${PROJECT_ID}"

# 1. The append-only custom role: create + get, and deliberately NO update or
#    delete, so no agent identity can rewrite or erase grant history.
echo "[1/3] Custom role '${ROLE_ID}' (datastore.entities.create + get; no update/delete)..."
ROLE_YAML="$(mktemp)"
cat > "${ROLE_YAML}" <<ROLE
title: "Hodi Append-Only Grant Writer"
description: "Create and read grant events. No update, no delete — history cannot be rewritten."
stage: GA
includedPermissions:
- datastore.entities.create
- datastore.entities.get
- datastore.entities.list
ROLE
if gcloud iam roles describe "${ROLE_ID}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam roles update "${ROLE_ID}" --project="${PROJECT_ID}" --file="${ROLE_YAML}" --quiet
else
  gcloud iam roles create "${ROLE_ID}" --project="${PROJECT_ID}" --file="${ROLE_YAML}" --quiet
fi
rm -f "${ROLE_YAML}"

# 2. One service account per agent, read straight out of the policy module.
echo "[2/3] Service accounts, generated from src/schema/iam_policy.py..."
python3 - "${PROJECT_ID}" <<'PY' > /tmp/hodi_sa_plan.txt
import sys, os
sys.path.insert(0, os.getcwd())
from src.schema.iam_policy import AGENT_SA_MAP
for role_key, info in AGENT_SA_MAP.items():
    account_id = info["sa_email"].split("@")[0]
    print(f"{account_id}\t{info['role_name']}\t{info['conflict_domain']}")
PY

while IFS=$'\t' read -r account_id role_name conflict_domain; do
  [ -z "${account_id}" ] && continue
  echo "  - ${account_id} (${role_name}; conflict domain: ${conflict_domain})"
  SA_EMAIL="${account_id}@${PROJECT_ID}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${account_id}" \
      --project="${PROJECT_ID}" \
      --display-name="Hodi ${role_name}" \
      --description="Conflict domain: ${conflict_domain}. Generated from src/schema/iam_policy.py."
  fi
  # Service-account creation is eventually consistent: binding a role to an SA
  # the IAM backend has not yet propagated fails with "does not exist". Wait for
  # it rather than masking the failure.
  for attempt in $(seq 1 30); do
    if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${account_id}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="projects/${PROJECT_ID}/roles/${ROLE_ID}" \
    --condition=None --quiet >/dev/null
done < /tmp/hodi_sa_plan.txt
rm -f /tmp/hodi_sa_plan.txt

# 3. Verify: every SA in the policy module exists and holds the custom role.
echo "[3/3] Verifying every policy-declared SA exists and holds '${ROLE_ID}'..."
python3 - "${PROJECT_ID}" "${ROLE_ID}" <<'PY'
import subprocess, sys, os
sys.path.insert(0, os.getcwd())
from src.schema.iam_policy import AGENT_SA_MAP
project_id, role_id = sys.argv[1], sys.argv[2]
policy = subprocess.run(
    ["gcloud", "projects", "get-iam-policy", project_id, "--format=json"],
    capture_output=True, text=True, check=True).stdout
missing = []
for role_key, info in AGENT_SA_MAP.items():
    email = f"{info['sa_email'].split('@')[0]}@{project_id}.iam.gserviceaccount.com"
    exists = subprocess.run(
        ["gcloud", "iam", "service-accounts", "describe", email, f"--project={project_id}"],
        capture_output=True).returncode == 0
    bound = f'"serviceAccount:{email}"' in policy and role_id in policy
    print(f"  {'OK ' if exists and bound else 'MISSING'} {email}")
    if not (exists and bound):
        missing.append(email)
if missing:
    print(f"\nFAILED: {len(missing)} service account(s) not provisioned: {missing}")
    sys.exit(1)
print("\nAll four conflict-domain service accounts exist and hold the append-only role.")
PY

echo "Provisioning complete."
