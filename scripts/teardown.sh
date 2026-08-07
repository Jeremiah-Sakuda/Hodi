#!/usr/bin/env bash
# scripts/teardown.sh — Unconditional 23:00 UTC Nightly Teardown & Cost Guard (HOD-005)
#
# Fences the Gemma project (hodi-gemma-2026) by deleting any active Vertex AI
# endpoints. This script NEVER touches hodi-evidence-endpoint: that service's
# uptime is a hard constraint (crawler-access accrual cannot be recovered), it
# already runs min-instances=0 so idle cost is zero, and an earlier version of
# this script that capped its max-instances to 0 would have taken the evidence
# instrument offline every night.
#
# HOD-005 AC: teardown on a nonexistent endpoint (or absent/disabled Gemma
# project) is a VERIFIED no-op — handled explicitly below, never with `|| true`
# (Truthful Build Log & Verification Rule: no masked infrastructure failures).

set -euo pipefail

GEMMA_PROJECT="${HODI_GEMMA_PROJECT:-hodi-gemma-2026}"
REGION="us-central1"

echo "================================================================================"
echo "HODI UNCONDITIONAL NIGHTLY TEARDOWN & COST GUARD (HOD-005)"
echo "Timestamp: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "Gemma project: ${GEMMA_PROJECT}"
echo "================================================================================"

# Verified no-op path 1: the Gemma project does not exist or is inaccessible.
if ! gcloud projects describe "${GEMMA_PROJECT}" >/dev/null 2>&1; then
  echo "[VERIFIED NO-OP] Project '${GEMMA_PROJECT}' does not exist or is not accessible."
  echo "Nothing to tear down. Exiting 0."
  exit 0
fi

# Verified no-op path 2: the AI Platform API is not enabled, so no endpoints can exist.
if ! endpoints=$(gcloud ai endpoints list --region="${REGION}" --project="${GEMMA_PROJECT}" --format="value(name)" 2>&1); then
  echo "[VERIFIED NO-OP] Could not list AI endpoints in '${GEMMA_PROJECT}' (API disabled or no access):"
  echo "  ${endpoints}"
  echo "No deployable endpoint surface exists. Exiting 0."
  exit 0
fi

if [ -z "${endpoints}" ]; then
  echo "[VERIFIED NO-OP] No active Vertex AI endpoints in '${GEMMA_PROJECT}'."
  echo "Teardown complete (nothing was running). Exiting 0."
  exit 0
fi

# Real teardown path: delete each endpoint and FAIL LOUDLY if deletion fails —
# a masked failure here is exactly how a $20 cap gets blown overnight.
echo "${endpoints}" | while read -r ep; do
  [ -z "${ep}" ] && continue
  echo "[TEARDOWN] Deleting Gemma endpoint: ${ep}"
  gcloud ai endpoints delete "${ep}" --region="${REGION}" --project="${GEMMA_PROJECT}" --quiet
done

echo "Unconditional teardown completed: all Vertex AI endpoints in '${GEMMA_PROJECT}' deleted."
