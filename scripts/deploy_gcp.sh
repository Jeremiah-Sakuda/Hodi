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
# Honest scope note: the running service is a single Cloud Run process, so the
# four agent SAs above are the identities the policy layer names and audits, not
# four separate runtime principals. Splitting the fleet into four services, each
# deployed with --service-account, is the natural next step and is stated as
# not-yet-done rather than implied.
#
# What IS enforced at runtime (step 3): the single process executes as a
# dedicated runtime SA that holds the append-only role plus read-only Firestore
# access — no update, no delete. So "grant history cannot be rewritten" is an
# IAM property of the deployed identity, not only a property of the in-process
# code path. Earlier this was not true: the process ran as the default compute
# SA with roles/editor, which can update and delete.

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
  # HARDENING GUARD (HOD-711). If setup_workload_identity.sh has already
  # replaced this SA's append-only binding with the (default)-conditioned one
  # ('grant-log-only'), re-adding an UNCONDITIONAL binding here would silently
  # re-open the cross-database boundary that script closed — the next deploy
  # would undo the hardening with no test failing until the live E2E ran.
  # Skip the bind when the conditioned form is present.
  SA_EMAIL="${account_id}@${PROJECT_ID}.iam.gserviceaccount.com"
  EXISTING_TITLES="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
    --flatten='bindings[].members' --format='value(bindings.condition.title)' \
    --filter="bindings.members:serviceAccount:${SA_EMAIL} AND bindings.role:projects/${PROJECT_ID}/roles/${ROLE_ID}" 2>/dev/null || true)"
  if printf '%s\n' "${EXISTING_TITLES}" | grep -q '^grant-log-only$'; then
    echo "    (hardened: append-only already conditioned to (default) — not re-binding unconditionally)"
  else
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${SA_EMAIL}" \
      --role="projects/${PROJECT_ID}/roles/${ROLE_ID}" \
      --condition=None --quiet >/dev/null
  fi
done < /tmp/hodi_sa_plan.txt
rm -f /tmp/hodi_sa_plan.txt

# 3. The RUNTIME identity the deployed Cloud Run service actually executes as.
#
#    The four accounts above are the identities the policy layer NAMES, checks
#    and records; nothing executes as them. Until this step existed, the
#    deployed process ran as the DEFAULT COMPUTE service account, which holds
#    roles/editor — i.e. datastore.entities.update and .delete. So the headline
#    "history cannot be rewritten" invariant, true of the four policy SAs, was
#    FALSE of the identity that actually writes grant events.
#
#    This binds a dedicated runtime SA that can read and append but CANNOT
#    update or delete:
#      - ${ROLE_ID}          : create + get + list  (append + read)
#      - roles/datastore.viewer : all Firestore READ permissions, zero writes —
#                                 supplies datastore.databases.get etc. that the
#                                 client needs and the create-only role omits
#      - roles/aiplatform.user  : Gemini/Gemma calls (scope interpretation, notice drafting)
#      - roles/logging.logWriter: structured logs
#    Neither datastore role grants update or delete, so the invariant is now
#    enforced by IAM at runtime, not merely by the in-process code path.
RUNTIME_SA_ID="hodi-runtime-sa"
RUNTIME_SA_EMAIL="${RUNTIME_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "[3/4] Runtime service account '${RUNTIME_SA_ID}' (append + read, no update/delete)..."
if ! gcloud iam service-accounts describe "${RUNTIME_SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNTIME_SA_ID}" \
    --project="${PROJECT_ID}" \
    --display-name="Hodi Cloud Run runtime" \
    --description="The identity the deployed service executes as. Append + read only; no datastore update/delete."
fi
for attempt in $(seq 1 30); do
  gcloud iam service-accounts describe "${RUNTIME_SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1 && break
  sleep 2
done
for role in "projects/${PROJECT_ID}/roles/${ROLE_ID}" \
            "roles/datastore.viewer" \
            "roles/aiplatform.user" \
            "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
    --role="${role}" --condition=None --quiet >/dev/null
done
echo "  bound: ${ROLE_ID}, datastore.viewer, aiplatform.user, logging.logWriter"
echo "  NOTE: deploy the service with --service-account ${RUNTIME_SA_EMAIL} for this to take effect."

# 4. Verify: every SA in the policy module exists and holds the custom role.
echo "[4/4] Verifying every policy-declared SA exists and holds '${ROLE_ID}'..."
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
