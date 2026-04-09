#!/bin/bash
# ============================================
# A2A Agent - Google Cloud Run Deploy Script
# ============================================

set -e

# ─── Configuration (edit these) ───
PROJECT_ID="sn-63991000-aia-aif-7haf"       # <-- Change this
REGION="us-central1"
SERVICE_NAME="it-incident-helper"
API_KEY="snow-1234"      # <-- Change this to a strong key

# ─── Step 1: Set project ───
echo ">>> Setting GCP project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# ─── Step 2: Deploy to Cloud Run ───
echo ">>> Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "AGENT_API_KEY=$API_KEY" \
  --memory 512Mi

# ─── Step 3: Get the service URL and update env ───
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --format "value(status.url)")

echo ">>> Updating SERVICE_URL env var..."
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --set-env-vars "AGENT_API_KEY=$API_KEY,SERVICE_URL=$SERVICE_URL"

echo ""
echo "============================================"
echo "  DEPLOYED SUCCESSFULLY"
echo "============================================"
echo "  Service URL : $SERVICE_URL"
echo "  Agent Card  : $SERVICE_URL/.well-known/agent.json"
echo "  API Key     : $API_KEY"
echo "============================================"
echo ""
echo ">>> Test commands:"
echo ""
echo "# 1. Check agent card (no auth needed):"
echo "curl $SERVICE_URL/.well-known/agent.json"
echo ""
echo "# 2. Send a task (auth required):"
echo "curl -X POST $SERVICE_URL/tasks/send \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -H 'x-api-key: $API_KEY' \\"
echo "  -d '{\"jsonrpc\":\"2.0\",\"id\":\"test-1\",\"method\":\"tasks/send\",\"params\":{\"id\":\"task-001\",\"message\":{\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"VPN is down for engineering team\"}]}}}'"
echo ""
