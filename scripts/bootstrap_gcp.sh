#!/bin/bash
set -e

PROJECT_ID=${GCP_PROJECT_ID:-hodi-2026}
echo "Bootstrapping GCP Project: $PROJECT_ID"

# Enable required APIs
gcloud services enable \
    firestore.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    --project=$PROJECT_ID



echo "Bootstrap complete."
