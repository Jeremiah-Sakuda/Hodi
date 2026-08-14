#!/usr/bin/env bash
# scripts/setup_release_verification.sh — Workload Identity Federation for the
# live release-verification workflow (HOD-720).
#
# WHAT THIS BUILDS. The keyless trust path that lets .github/workflows/verify-live.yml
# authenticate to hodi-2026 without a service-account JSON key anywhere:
#
#   GitHub OIDC token  ->  WIF provider (attribute-CONDITIONED to this repo)
#                      ->  principalSet binding on release-verifier-sa
#                      ->  short-lived Google access token
#
# WHY CONDITIONED, STATED PLAINLY. A WIF provider with no attribute condition
# trusts *every* GitHub repository on the internet, and a principalSet binding
# written as `attribute.repository/*` grants that trust to the service account.
# This project already learned that lesson the expensive way once: the per-domain
# Firestore bindings were created unconditionally, so an IAM *condition* narrowed
# nothing because a broad grant sat beside it, and the workload-identity E2E
# failed its first proof (docs/FINDINGS.md). The same mistake here would not fail
# a test — it would hand any repo on GitHub a token for this project. So the
# condition is set at provider creation, the binding names exactly one
# repository, and step 4 reads both back and refuses to exit 0 unless the
# narrowing is actually present.
#
# LEAST PRIVILEGE. The verifier reads deployments and the public key, and writes
# only to the collections the E2E suite is documented to write to. It is not an
# owner, and it holds no key that outlives a workflow run.
#
# IDEMPOTENT. Safe to re-run; every create is guarded by a read.
#
# Usage:  bash scripts/setup_release_verification.sh
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hodi-2026}"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
REPO="${HODI_GITHUB_REPO:-Jeremiah-Sakuda/Hodi}"
POOL="github-actions"
PROVIDER="github-oidc"
SA_NAME="release-verifier-sa"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
LOCATION="global"

ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$1"; }
info() { printf '  [--]  %s\n' "$1"; }
die()  { printf '  \033[31m[FAIL]\033[0m %s\n' "$1" >&2; exit 1; }

echo "=============================================================================="
echo "RELEASE VERIFICATION IDENTITY — $PROJECT_ID  <-  github.com/$REPO"
echo "=============================================================================="

echo
echo "[1] APIs"
# cloudresourcemanager is here because of a failure worth naming: the
# append-only IAM proof (tests/test_grant_log_iam.py) reads the project policy,
# and that had only ever run from a developer laptop, where USER credentials
# take a different quota path. From a service identity it could not run at all
# — the API had never been enabled on this project. A check that only passes
# under one particular set of credentials is not a property of the system.
for api in iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com; do
  if gcloud services list --enabled --project="$PROJECT_ID" --format='value(config.name)' \
       | grep -qx "$api"; then
    ok "$api already enabled"
  else
    gcloud services enable "$api" --project="$PROJECT_ID" --quiet
    ok "$api enabled"
  fi
done

echo
echo "[2] workload identity pool and provider"
if gcloud iam workload-identity-pools describe "$POOL" \
     --location="$LOCATION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "pool '$POOL' exists"
else
  gcloud iam workload-identity-pools create "$POOL" \
    --location="$LOCATION" --project="$PROJECT_ID" \
    --display-name="GitHub Actions" \
    --description="Keyless OIDC federation for release verification (HOD-720)" --quiet
  ok "pool '$POOL' created"
fi

# The condition is the security boundary. Without it this provider would mint
# credentials for a workflow in ANY repository.
CONDITION="assertion.repository == '${REPO}'"
if gcloud iam workload-identity-pools providers describe "$PROVIDER" \
     --workload-identity-pool="$POOL" --location="$LOCATION" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "provider '$PROVIDER' exists"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --workload-identity-pool="$POOL" --location="$LOCATION" --project="$PROJECT_ID" \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="$CONDITION" --quiet
  ok "provider '$PROVIDER' created, conditioned to $REPO"
fi

echo
echo "[3] verifier service account and least-privilege roles"
if gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "service account exists: $SA"
else
  gcloud iam service-accounts create "$SA_NAME" --project="$PROJECT_ID" \
    --display-name="Hodi Release Verifier" \
    --description="Runs live release verification from CI via WIF. No key." --quiet
  ok "service account created: $SA"
fi

# Deliberately narrow. Read what is deployed, read the public key, and write only
# to the collections the E2E suite is documented to write to.
# roles/iam.securityReviewer is READ-ONLY on IAM. It is here because
# tests/test_grant_log_iam.py proves the deployed runtime identity holds no
# datastore update/delete by READING the project policy; without it the test
# errors in setUpClass and the append-only claim goes unproven in CI.
for role in roles/run.viewer \
            roles/cloudkms.publicKeyViewer \
            roles/datastore.user \
            roles/logging.viewer \
            roles/iam.securityReviewer \
            roles/cloudscheduler.viewer; do
  if gcloud projects get-iam-policy "$PROJECT_ID" \
       --flatten="bindings[].members" \
       --filter="bindings.role=$role AND bindings.members:serviceAccount:$SA" \
       --format='value(bindings.role)' | grep -q .; then
    ok "$role already bound"
  else
    # --condition=None is REQUIRED and is not a loosening: this project's policy
    # already contains conditional bindings (the per-domain Firestore grants), and
    # gcloud refuses an unconditioned add against a conditioned policy unless the
    # absence of a condition is stated explicitly. These roles are project-wide by
    # intent; the narrowing that matters is on the impersonation binding in step 4.
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$SA" --role="$role" --condition=None --quiet >/dev/null
    ok "$role bound"
  fi
done

echo
echo "[4] the binding that lets exactly one repository impersonate it"
PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}"
# BOTH roles are required, and the second is not redundant. workloadIdentityUser
# lets the federated principal *be* this service account; token_format:access_token
# makes google-github-actions/auth call generateAccessToken, whose permission
# (iam.serviceAccounts.getAccessToken) lives in serviceAccountTokenCreator. The
# first run failed with exactly that PERMISSION_DENIED — the federation was
# accepted and the token mint was not. Both are bound to the SAME narrowed
# principalSet, so this widens who-can-do-what, never who.
for wif_role in roles/iam.workloadIdentityUser roles/iam.serviceAccountTokenCreator; do
  gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --project="$PROJECT_ID" --role="$wif_role" \
    --member="$PRINCIPAL" --quiet >/dev/null
  ok "${wif_role#roles/iam.} bound to attribute.repository/${REPO}"
done

echo
echo "[4b] impersonation of ONE fleet identity, to prove a denial"
# tests/test_workload_identity.py proves the evidence agent CANNOT read the
# identity database. Proving a denial requires being able to attempt it, so the
# verifier must be able to act as that one agent — and only that one.
#
# Stated plainly rather than buried: this is the largest privilege the verifier
# holds. It is bounded by the evidence agent's own scope, which the per-domain
# split already narrows to its own database, so the blast radius is exactly the
# thing the architecture claims to bound. It is granted PER SERVICE ACCOUNT, not
# project-wide, so it does not extend to the custodian, the negotiator or the
# propagator.
EVIDENCE_SA="evidence-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$EVIDENCE_SA" \
  --project="$PROJECT_ID" --role="roles/iam.serviceAccountTokenCreator" \
  --member="serviceAccount:$SA" --quiet >/dev/null
ok "verifier may impersonate ${EVIDENCE_SA} (only, and only to prove it is denied)"
for other in rights-custodian-sa licensing-negotiator-sa revocation-propagator-sa consent-arbiter-sa; do
  if gcloud iam service-accounts get-iam-policy "${other}@${PROJECT_ID}.iam.gserviceaccount.com" \
       --project="$PROJECT_ID" --flatten='bindings[].members' \
       --filter="bindings.members:serviceAccount:$SA" \
       --format='value(bindings.role)' 2>/dev/null | grep -q .; then
    die "verifier can impersonate ${other} — it was scoped to the evidence agent alone."
  fi
done
ok "verifier cannot impersonate the other four domain identities"

echo
echo "[5] PROOF — the narrowing is present, read back from IAM"
ACTUAL_CONDITION="$(gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --workload-identity-pool="$POOL" --location="$LOCATION" --project="$PROJECT_ID" \
  --format='value(attributeCondition)')"
if [ -z "$ACTUAL_CONDITION" ]; then
  die "provider has NO attribute condition — it would trust every repository on GitHub."
fi
case "$ACTUAL_CONDITION" in
  *"$REPO"*) ok "provider condition names this repo only: $ACTUAL_CONDITION" ;;
  *) die "provider condition does not name $REPO: $ACTUAL_CONDITION" ;;
esac

MEMBERS="$(gcloud iam service-accounts get-iam-policy "$SA" --project="$PROJECT_ID" \
  --flatten='bindings[].members' \
  --filter='bindings.role:roles/iam.workloadIdentityUser OR bindings.role:roles/iam.serviceAccountTokenCreator' \
  --format='value(bindings.members)')"
echo "$MEMBERS" | while read -r m; do
  [ -z "$m" ] && continue
  case "$m" in
    *"attribute.repository/${REPO}") ;;
    *"/*"|*"attribute.repository/*")
      die "a wildcard principalSet ($m) can impersonate the verifier — remove it." ;;
    *) info "other member present: $m" ;;
  esac
done
ok "no wildcard principalSet on the verifier"

if gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
     --filter="bindings.members:serviceAccount:$SA AND bindings.role:roles/owner" \
     --format='value(bindings.role)' | grep -q .; then
  die "the verifier holds roles/owner — that is the defect class this repo removes."
fi
ok "verifier is not an owner"

echo
echo "=============================================================================="
echo "Set these as GitHub repository variables (gh variable set <NAME> --body '<v>'):"
echo "  WIF_PROVIDER              projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
echo "  VERIFIER_SERVICE_ACCOUNT  ${SA}"
echo "=============================================================================="
