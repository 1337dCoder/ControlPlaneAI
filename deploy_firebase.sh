#!/usr/bin/env bash
# ==============================================================================
# ControlPlane AI — Automated Firebase & Google Cloud Run Deployment Script
# ==============================================================================
set -e

PROJECT_ID=$1
REGION=${2:-"us-central1"}
SERVICE_NAME="controlplane-api"

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Error: Firebase / Google Cloud Project ID required."
  echo "Usage: ./deploy_firebase.sh <PROJECT_ID> [REGION]"
  echo "Example: ./deploy_firebase.sh my-controlplane-project us-central1"
  exit 1
fi

echo "======================================================================"
echo "🚀 Deploying ControlPlane to Firebase / Google Cloud Run"
echo "Project ID:   $PROJECT_ID"
echo "Region:       $REGION"
echo "Service Name: $SERVICE_NAME"
echo "======================================================================"

# 1. Update .firebaserc
cat <<EOF > .firebaserc
{
  "projects": {
    "default": "$PROJECT_ID"
  }
}
EOF

# 2. Update firebase.json region
cat <<EOF > firebase.json
{
  "hosting": {
    "public": "app/static",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "run": {
          "serviceId": "$SERVICE_NAME",
          "region": "$REGION"
        }
      }
    ]
  }
}
EOF

# 3. Build & Deploy Backend Container to Cloud Run
echo "📦 [1/2] Building and deploying backend container to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production,DATABASE_PATH=/tmp/controlplane.db"

# 4. Deploy Firebase Hosting
echo "🌐 [2/2] Deploying Firebase Hosting rewrites..."
firebase deploy --only hosting --project "$PROJECT_ID"

echo "======================================================================"
echo "🎉 DEPLOYMENT COMPLETE!"
echo "Your app is live on Firebase Hosting: https://$PROJECT_ID.web.app"
echo "======================================================================"
