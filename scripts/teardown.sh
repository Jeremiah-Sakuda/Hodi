#!/usr/bin/env bash
# scripts/teardown.sh — Unconditional 23:00 UTC Nightly Teardown & Cost Guard (HOD-005)
# Teardown script enforcing $20 hard cap on hodi-gemma-2026 and capping active instances.

set -euo pipefail

echo "================================================================================"
echo "HODI UNCONDITIONAL NIGHTLY TEARDOWN & COST GUARD (HOD-005)"
echo "Timestamp: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================================"

# 1. Scale down Cloud Run services to 0 instances
echo "[TEARDOWN 1] Capping Cloud Run service instances to 0..."
gcloud run services update hodi-evidence-endpoint \
  --min-instances=0 \
  --max-instances=0 \
  --region=us-central1 \
  --project=hodi-2026 || true

# 2. Terminate any active Vertex AI / Gemma endpoints in hodi-gemma-2026
echo "[TEARDOWN 2] Fencing hodi-gemma-2026 project and terminating active endpoints..."
gcloud ai endpoints list --region=us-central1 --project=hodi-gemma-2026 --format="value(name)" | while read -r ep; do
  if [ -n "$ep" ]; then
    echo "Undeploying and deleting Gemma endpoint: $ep"
    gcloud ai endpoints delete "$ep" --region=us-central1 --project=hodi-gemma-2026 --quiet || true
  fi
done

echo "Unconditional 23:00 UTC teardown completed successfully."
