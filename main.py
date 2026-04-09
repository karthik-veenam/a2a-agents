import os
import uuid
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="IT Incident Helper - A2A Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config from environment
API_KEY = os.environ.get("AGENT_API_KEY", "test-key-change-me")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:8080")

# System prompt for the IT Incident Helper agent
SYSTEM_PROMPT = """You are an IT Incident Helper agent deployed in an enterprise environment. Your job is to:

1. **Triage** incoming IT incidents - classify by category and priority
2. **Diagnose** the likely root cause
3. **Provide resolution steps** - clear, numbered, actionable steps
4. **Escalate** if the issue is beyond self-service resolution

Categories: VPN/Network Access, Identity & Access, Email/Collaboration, Network/Connectivity, Hardware/Peripherals, Performance, Software Requests, Application Errors, Security Incidents, General IT Support

Priority levels:
- P1 Critical: Complete service outage affecting multiple users/teams
- P2 High: Major feature broken, no workaround, single user or small team
- P3 Medium: Feature degraded but workaround exists
- P4 Low: Minor issue, cosmetic, or feature request

Always respond in this structured format:
**Incident Triage**
- Category: [category]
- Priority: [P1/P2/P3/P4 - label]
- Affected scope: [individual/team/department/org-wide]

**Diagnosis**
[Brief root cause analysis]

**Resolution Steps**
1. [Step 1]
2. [Step 2]
...

**Escalation**
[Whether this needs escalation and to which team, or if self-service resolution is sufficient]

Be concise, professional, and actionable. If the issue description is vague, still provide your best triage and ask clarifying questions at the end."""


# ─── Middleware: API Key check (skip for agent card and health) ───
@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.url.path in ("/.well-known/agent.json", "/health"):
        return await call_next(request)

    api_key = request.headers.get("x-api-key")
    if api_key != API_KEY:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or missing API key"}
        )
    return await call_next(request)


# ─── Agent Card ───
@app.get("/.well-known/agent.json")
async def agent_card():
    return {
        "name": "IT Incident Helper",
        "description": "AI-powered IT incident triage and resolution agent. Classifies incidents, diagnoses root causes, and provides step-by-step resolution guidance.",
        "url": SERVICE_URL,
        "version": "2.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False
        },
        "skills": [
            {
                "id": "incident-triage",
                "name": "Incident Triage & Resolution",
                "description": "AI-powered classification, diagnosis, and resolution of IT incidents",
                "examples": [
                    "VPN is not connecting for the engineering team",
                    "Cannot access email since this morning",
                    "Need password reset for SAP",
                    "Laptop running extremely slow after update",
                    "Printer on 3rd floor not responding"
                ]
            }
        ],
        "authentication": {
            "schemes": ["apiKey"],
            "credentials": "API key via x-api-key header"
        }
    }


# ─── Call Claude API ───
async def ask_claude(user_message: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "Error: ANTHROPIC_API_KEY not configured. Set it in environment variables."

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            }
        )

    if response.status_code != 200:
        return f"Error calling Claude API: {response.status_code} - {response.text}"

    data = response.json()
    return "".join(
        block["text"] for block in data.get("content", []) if block.get("type") == "text"
    )


# ─── A2A Task Handler ───
@app.post("/tasks/send")
async def handle_task(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    if body.get("jsonrpc") != "2.0" or body.get("method") != "tasks/send":
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON-RPC request"}
        )

    params = body.get("params", {})
    task_id = params.get("id", str(uuid.uuid4()))
    message = params.get("message", {})
    parts = message.get("parts", [])

    user_text = ""
    for part in parts:
        if part.get("type") == "text":
            user_text += part.get("text", "")

    if not user_text:
        return _error_response(body.get("id"), task_id, "No text content in message")

    # Call Claude for AI-powered triage
    agent_response = await ask_claude(user_text)

    return {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "id": task_id,
            "status": {"state": "completed"},
            "artifacts": [
                {
                    "parts": [{"type": "text", "text": agent_response}]
                }
            ]
        }
    }


# ─── Health check ───
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "llm_configured": bool(ANTHROPIC_API_KEY)
    }


def _error_response(rpc_id, task_id, message):
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "id": task_id,
            "status": {
                "state": "failed",
                "message": {"role": "agent", "parts": [{"type": "text", "text": message}]}
            }
        }
    }
