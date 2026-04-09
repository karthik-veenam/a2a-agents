import os
import uuid
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="IT Incident Helper - A2A Agent")

# API Key from environment variable
API_KEY = os.environ.get("AGENT_API_KEY", "test-key-change-me")

# Service URL (set during deploy)
SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:8080")


# ─── Middleware: API Key check (skip for agent card) ───
@app.middleware("http")
async def check_api_key(request: Request, call_next):
    # Agent card is public so other agents can discover this agent
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
        "description": "Triages and resolves common IT incidents - VPN, password resets, connectivity, software installs",
        "url": SERVICE_URL,
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False
        },
        "skills": [
            {
                "id": "incident-triage",
                "name": "Incident Triage",
                "description": "Classifies IT incidents by category and priority",
                "examples": [
                    "VPN is not connecting",
                    "Cannot access email",
                    "Need password reset"
                ]
            },
            {
                "id": "incident-resolution",
                "name": "Incident Resolution",
                "description": "Provides step-by-step resolution for common IT issues",
                "examples": [
                    "How to fix slow internet",
                    "Outlook keeps crashing",
                    "Printer not found"
                ]
            }
        ],
        "authentication": {
            "schemes": ["apiKey"],
            "credentials": "API key via x-api-key header"
        }
    }


# ─── A2A Task Handler ───
@app.post("/tasks/send")
async def handle_task(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    # Validate JSON-RPC structure
    if body.get("jsonrpc") != "2.0" or body.get("method") != "tasks/send":
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON-RPC request"}
        )

    params = body.get("params", {})
    task_id = params.get("id", str(uuid.uuid4()))
    message = params.get("message", {})
    parts = message.get("parts", [])

    # Extract text from message parts
    user_text = ""
    for part in parts:
        if part.get("type") == "text":
            user_text += part.get("text", "")

    if not user_text:
        return _error_response(body.get("id"), task_id, "No text content in message")

    # ─── Your agent logic here ───
    category, priority = triage_incident(user_text)
    resolution = get_resolution(category)

    response_text = (
        f"**Incident Triaged**\n"
        f"- Category: {category}\n"
        f"- Priority: {priority}\n"
        f"- Suggested Resolution: {resolution}"
    )

    return {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "id": task_id,
            "status": {"state": "completed"},
            "artifacts": [
                {
                    "parts": [{"type": "text", "text": response_text}]
                }
            ]
        }
    }


# ─── Health check ───
@app.get("/health")
async def health():
    return {"status": "healthy"}


# ─── Agent Logic (replace with your actual logic / LLM calls) ───
INCIDENT_KEYWORDS = {
    "vpn": ("VPN / Network Access", "P2 - High"),
    "password": ("Identity & Access", "P3 - Medium"),
    "email": ("Email / Collaboration", "P2 - High"),
    "outlook": ("Email / Collaboration", "P2 - High"),
    "printer": ("Hardware / Peripherals", "P4 - Low"),
    "wifi": ("Network / Connectivity", "P2 - High"),
    "internet": ("Network / Connectivity", "P2 - High"),
    "slow": ("Performance", "P3 - Medium"),
    "install": ("Software Requests", "P4 - Low"),
    "access": ("Identity & Access", "P3 - Medium"),
    "login": ("Identity & Access", "P2 - High"),
    "crash": ("Application Errors", "P2 - High"),
    "error": ("Application Errors", "P3 - Medium"),
}


def triage_incident(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    for keyword, (category, priority) in INCIDENT_KEYWORDS.items():
        if keyword in text_lower:
            return category, priority
    return "General IT Support", "P3 - Medium"


RESOLUTIONS = {
    "VPN / Network Access": "1) Disconnect and reconnect VPN. 2) Restart your machine. 3) Check if VPN client needs an update. 4) Try a different network.",
    "Identity & Access": "1) Try 'Forgot Password' on the login page. 2) Clear browser cache. 3) Check Caps Lock. 4) If locked out, contact IT for account unlock.",
    "Email / Collaboration": "1) Check Outlook connection status. 2) Restart Outlook. 3) Clear Outlook cache. 4) Try Outlook on the web.",
    "Network / Connectivity": "1) Toggle Wi-Fi off/on. 2) Forget and rejoin the network. 3) Restart router if on home network. 4) Try a wired connection.",
    "Hardware / Peripherals": "1) Check physical connections. 2) Reinstall printer driver. 3) Restart print spooler service. 4) Try printing from a different app.",
    "Performance": "1) Close unnecessary apps. 2) Check Task Manager for high CPU/memory. 3) Restart your machine. 4) Clear temp files.",
    "Software Requests": "1) Check the self-service software portal. 2) Submit a software request ticket. 3) Provide business justification if needed.",
    "Application Errors": "1) Restart the application. 2) Check for updates. 3) Clear app cache. 4) Reinstall if persistent.",
}


def get_resolution(category: str) -> str:
    return RESOLUTIONS.get(category, "Please submit a ticket and an IT engineer will investigate.")


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
