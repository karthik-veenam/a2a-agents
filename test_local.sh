#!/bin/bash
# ============================================
# Local Test Script for A2A Agent
# ============================================
# Run this AFTER starting the server locally:
#   pip install -r requirements.txt
#   AGENT_API_KEY=test123 uvicorn main:app --port 8080
# ============================================

BASE_URL="http://localhost:8080"
API_KEY="test123"

echo "─── Test 1: Agent Card (no auth) ───"
curl -s "$BASE_URL/.well-known/agent.json" | python3 -m json.tool
echo ""

echo "─── Test 2: Health Check ───"
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

echo "─── Test 3: Task WITHOUT api key (should fail 401) ───"
curl -s -X POST "$BASE_URL/tasks/send" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/send","params":{"id":"t1","message":{"role":"user","parts":[{"type":"text","text":"VPN is down"}]}}}' \
  | python3 -m json.tool
echo ""

echo "─── Test 4: VPN Incident (should triage as P2) ───"
curl -s -X POST "$BASE_URL/tasks/send" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"jsonrpc":"2.0","id":"2","method":"tasks/send","params":{"id":"t2","message":{"role":"user","parts":[{"type":"text","text":"VPN is not connecting for the engineering team"}]}}}' \
  | python3 -m json.tool
echo ""

echo "─── Test 5: Password Reset (should triage as P3) ───"
curl -s -X POST "$BASE_URL/tasks/send" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"jsonrpc":"2.0","id":"3","method":"tasks/send","params":{"id":"t3","message":{"role":"user","parts":[{"type":"text","text":"I forgot my password and cannot login"}]}}}' \
  | python3 -m json.tool
echo ""

echo "─── Test 6: Printer Issue (should triage as P4) ───"
curl -s -X POST "$BASE_URL/tasks/send" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"jsonrpc":"2.0","id":"4","method":"tasks/send","params":{"id":"t4","message":{"role":"user","parts":[{"type":"text","text":"Printer on 3rd floor is not showing up"}]}}}' \
  | python3 -m json.tool
echo ""

echo "─── Test 7: Unknown Issue (should default to General) ───"
curl -s -X POST "$BASE_URL/tasks/send" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"jsonrpc":"2.0","id":"5","method":"tasks/send","params":{"id":"t5","message":{"role":"user","parts":[{"type":"text","text":"My desk phone has no dial tone"}]}}}' \
  | python3 -m json.tool
echo ""

echo "─── All tests complete ───"
