#!/usr/bin/env bash
# scripts/setup_kms_signing.sh — provision the Cloud KMS signing key (HOD-706).
#
# ONE command, run by the operator with ambient gcloud auth. Creates an
# asymmetric ECDSA-P256/SHA-256 signing key, grants roles/cloudkms.signer to
# the RUNTIME service account ONLY (nobody else can mint signatures — that is
# the whole point), prints the environment the service needs, and PROVES the
# result before reporting success: it fetches the public key and asserts the
# runtime SA holds signer while the four agent SAs hold nothing on the key.
#
# This script does not deploy. After it succeeds:
#   gcloud run services update hodi-evidence-endpoint --region "$REGION" \
#     --update-env-vars HODI_SIGNING=kms,HODI_KMS_KEY_VERSION=<printed below>
# (or add those two env vars to scripts/deploy.sh's deploy step).
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
LOCATION="${HODI_KMS_LOCATION:-us-central1}"
KEYRING="${HODI_KMS_KEYRING:-hodi-signing}"
KEY="${HODI_KMS_KEY:-hodi-provenance}"
RUNTIME_SA="${HODI_RUNTIME_SA:-hodi-runtime-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

echo "== Hodi KMS signing setup =="
echo "project=${PROJECT_ID} location=${LOCATION} keyring=${KEYRING} key=${KEY}"
echo "signer identity: ${RUNTIME_SA}"

gcloud services enable cloudkms.googleapis.com --project "${PROJECT_ID}"

if ! gcloud kms keyrings describe "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud kms keyrings create "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}"
fi

if ! gcloud kms keys describe "${KEY}" --keyring "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud kms keys create "${KEY}" \
    --keyring "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" \
    --purpose asymmetric-signing \
    --default-algorithm ec-sign-p256-sha256
fi

# Signer role to the runtime SA ONLY — plus publicKeyViewer, because
# roles/cloudkms.signer grants useToSign but NOT viewPublicKey: without the
# second role the service can mint signatures it cannot serve the verification
# key for, and /verification-key 500s (observed live 2026-08-14 — the deploy
# gate caught it).
for role in roles/cloudkms.signer roles/cloudkms.publicKeyViewer; do
  gcloud kms keys add-iam-policy-binding "${KEY}" \
    --keyring "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" \
    --member "serviceAccount:${RUNTIME_SA}" \
    --role "${role}" >/dev/null
done

KEY_VERSION="projects/${PROJECT_ID}/locations/${LOCATION}/keyRings/${KEYRING}/cryptoKeys/${KEY}/cryptoKeyVersions/1"

echo
echo "== PROOF, not report =="

# 1. The public key is fetchable (and is what recipients verify against).
gcloud kms keys versions get-public-key 1 \
  --key "${KEY}" --keyring "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" \
  --output-file /tmp/hodi-signing-public-key.pem
echo "public key fetched -> /tmp/hodi-signing-public-key.pem"

# 2. The runtime SA holds signer; the four agent SAs hold NOTHING on this key.
POLICY=$(gcloud kms keys get-iam-policy "${KEY}" \
  --keyring "${KEYRING}" --location "${LOCATION}" --project "${PROJECT_ID}" --format=json)
echo "${POLICY}" | grep -q "${RUNTIME_SA}" \
  || { echo "FAIL: runtime SA is not bound as signer"; exit 1; }
for sa in rights-custodian-sa licensing-negotiator-sa evidence-agent-sa revocation-propagator-sa; do
  if echo "${POLICY}" | grep -q "${sa}@"; then
    echo "FAIL: ${sa} holds a role on the signing key — only the runtime identity may sign"
    exit 1
  fi
done
echo "key IAM verified: signer=${RUNTIME_SA}, agent SAs hold nothing"

echo
echo "== Service configuration =="
echo "  HODI_SIGNING=kms"
echo "  HODI_KMS_KEY_VERSION=${KEY_VERSION}"
echo
echo "Deploy with both env vars set, then verify end to end:"
echo "  curl \$SERVICE_URL/verification-key"
echo "  python3 scripts/hodi_verify.py <exported-receipt.json> --key /tmp/hodi-signing-public-key.pem"
