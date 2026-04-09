import os
import uuid
import json
import re
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="A2A Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant. Be concise, accurate, and helpful. Use markdown formatting when it improves readability.

IMPORTANT — Status signaling:
At the very end of EVERY response, you MUST include exactly one of these tags on its own line:
[STATUS:completed] — Use when you have fully answered the user's request and no further input is needed.
[STATUS:input-required] — Use when you need more information, clarification, or are asking the user a follow-up question.

When to use [STATUS:input-required]:
- User says "hi", "hello", or a greeting — ask how you can help
- You need clarification: "What language?", "Can you share more details?"
- You're offering choices: "Would you like option A or B?"
- The task is multi-step and you need the next piece of info

When to use [STATUS:completed]:
- You've fully answered a question
- You've written the requested code, email, or content
- You've completed an analysis or explanation
- There's nothing left to ask — the task is done

The status tag MUST be the very last line. Never skip it."""

config = {
    "agent_api_key": os.environ.get("AGENT_API_KEY", "test-key-change-me"),
    "llm_provider": os.environ.get("LLM_PROVIDER", "anthropic"),
    "llm_model": os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"),
    "agent_name": os.environ.get("AGENT_NAME", "A2A Assistant"),
    "system_prompt": os.environ.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    "api_keys": {
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "google": os.environ.get("GOOGLE_API_KEY", ""),
    },
}

SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:8080")

PROVIDERS = {
    "anthropic": {"name": "Anthropic (Claude)", "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]},
    "openai": {"name": "OpenAI (GPT)", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    "google": {"name": "Google (Gemini)", "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]},
}

# In-memory conversation history per task
# Key: task_id → list of {"role": "user"/"assistant", "content": "..."}
conversations: dict[str, list[dict]] = {}


def parse_status(response_text: str) -> tuple[str, str]:
    """Extract status tag and clean response text."""
    match = re.search(r'\[STATUS:(completed|input-required)\]\s*$', response_text)
    if match:
        status = match.group(1)
        clean_text = response_text[:match.start()].rstrip()
        return clean_text, status
    # Default to completed if LLM forgot the tag
    return response_text, "completed"


# ═══════════════════════════════════════════════════════════════
# CONSOLE
# ═══════════════════════════════════════════════════════════════

CONSOLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2A Agent Console</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #08090a; color: #e0e0e0; min-height: 100vh; }}
        .hero {{ display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50vh; padding: 60px 20px 40px; text-align: center; background: radial-gradient(ellipse at 50% 0%, #1a1a3e 0%, #08090a 70%); }}
        .logo {{ width: 72px; height: 72px; background: linear-gradient(135deg, #6366f1, #8b5cf6); border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 36px; margin-bottom: 24px; box-shadow: 0 8px 32px #6366f133; }}
        .hero h1 {{ font-size: 36px; font-weight: 800; color: #fff; margin-bottom: 10px; }}
        .hero p {{ color: #888; font-size: 16px; max-width: 480px; line-height: 1.5; }}
        .status-badge {{ display: inline-flex; align-items: center; gap: 8px; margin-top: 20px; padding: 8px 16px; background: {status_bg}; border: 1px solid {status_border}; border-radius: 20px; font-size: 13px; font-weight: 500; color: {status_color}; }}
        .status-badge .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {status_color}; box-shadow: 0 0 6px {status_color}55; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; max-width: 900px; margin: 0 auto; padding: 0 20px 60px; }}
        .card {{ background: #111214; border: 1px solid #1e1f23; border-radius: 14px; padding: 24px; transition: border 0.2s, transform 0.2s; text-decoration: none; color: inherit; display: block; }}
        .card:hover {{ border-color: #333; transform: translateY(-2px); }}
        .card .icon {{ width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 14px; }}
        .card .icon.purple {{ background: #6366f122; }}
        .card .icon.green {{ background: #22c55e22; }}
        .card .icon.blue {{ background: #3b82f622; }}
        .card .icon.orange {{ background: #f9731622; }}
        .card h3 {{ font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 6px; }}
        .card p {{ font-size: 13px; color: #777; line-height: 1.4; }}
        .info-bar {{ max-width: 900px; margin: 0 auto 24px; padding: 0 20px; }}
        .info-bar .inner {{ background: #111214; border: 1px solid #1e1f23; border-radius: 12px; padding: 16px 20px; display: flex; align-items: center; gap: 12px; font-size: 13px; color: #888; }}
        .info-bar .tag {{ background: #6366f122; color: #a5b4fc; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
        .info-bar code {{ background: #1a1a1a; padding: 2px 8px; border-radius: 4px; color: #a5b4fc; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="hero">
        <div class="logo">⚡</div>
        <h1>{agent_name}</h1>
        <p>A2A-compliant AI agent with multi-turn conversations. Powered by {provider_name}.</p>
        <div class="status-badge"><div class="dot"></div>{status_text}</div>
    </div>
    <div class="info-bar"><div class="inner"><span class="tag">A2A</span><span>Agent URL: <code>{service_url}</code></span></div></div>
    <div class="grid">
        <a href="/config" class="card"><div class="icon purple">⚙️</div><h3>Configuration</h3><p>Set up LLM provider, API keys, model, and system prompt.</p></a>
        <a href="/.well-known/agent.json" class="card"><div class="icon green">📋</div><h3>Agent Card</h3><p>A2A agent card for discovery by other agents.</p></a>
        <a href="/health" class="card"><div class="icon blue">💓</div><h3>Health Check</h3><p>Agent status and LLM connection info.</p></a>
        <a href="/playground" class="card"><div class="icon orange">🧪</div><h3>Playground</h3><p>Test multi-turn conversations with your agent.</p></a>
    </div>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# PLAYGROUND
# ═══════════════════════════════════════════════════════════════

PLAYGROUND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Playground</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #08090a; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; }
        .topbar { padding: 14px 24px; border-bottom: 1px solid #1e1f23; display: flex; align-items: center; justify-content: space-between; }
        .topbar a { color: #6366f1; text-decoration: none; font-size: 13px; font-weight: 500; }
        .topbar h2 { font-size: 15px; font-weight: 600; color: #fff; }
        .topbar .task-id { font-size: 11px; color: #555; font-family: monospace; }
        .chat { flex: 1; max-width: 720px; width: 100%; margin: 0 auto; padding: 24px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
        .msg { max-width: 85%; padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
        .msg.user { align-self: flex-end; background: #6366f1; color: #fff; border-bottom-right-radius: 4px; }
        .msg.agent { align-self: flex-start; background: #1a1b1e; border: 1px solid #2a2b2e; color: #ddd; border-bottom-left-radius: 4px; }
        .msg.system { align-self: center; background: transparent; color: #666; font-size: 12px; text-align: center; }
        .status-pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-top: 6px; }
        .status-pill.completed { background: #22c55e22; color: #22c55e; }
        .status-pill.input-required { background: #eab30822; color: #eab308; }
        .input-bar { padding: 16px 20px; border-top: 1px solid #1e1f23; max-width: 720px; width: 100%; margin: 0 auto; display: flex; gap: 10px; }
        .input-bar input { flex: 1; padding: 12px 16px; background: #111214; border: 1px solid #2a2b2e; border-radius: 10px; color: #fff; font-size: 14px; font-family: inherit; }
        .input-bar input:focus { outline: none; border-color: #6366f1; }
        .input-bar button { padding: 12px 20px; background: #6366f1; color: #fff; border: none; border-radius: 10px; font-weight: 600; font-size: 14px; cursor: pointer; }
        .input-bar button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-reset { padding: 6px 12px; background: #1a1b1e; border: 1px solid #333; border-radius: 6px; color: #888; font-size: 12px; cursor: pointer; }
        .loading::after { content: '...'; animation: dots 1.2s steps(3, end) infinite; }
        @keyframes dots { 0% { content: '.'; } 33% { content: '..'; } 66% { content: '...'; } }
    </style>
</head>
<body>
    <div class="topbar">
        <a href="/console">&larr; Console</a>
        <h2>Agent Playground</h2>
        <button class="btn-reset" onclick="resetChat()">New Chat</button>
    </div>
    <div class="chat" id="chat">
        <div class="msg system">Send a message to start a conversation. The agent will signal when it needs more input or has completed your request.</div>
    </div>
    <div class="input-bar">
        <input type="text" id="input" placeholder="Type a message..." autofocus>
        <button id="send" onclick="send()">Send</button>
    </div>
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const btn = document.getElementById('send');
        let taskId = crypto.randomUUID();

        input.addEventListener('keydown', e => { if (e.key === 'Enter' && !btn.disabled) send(); });

        function resetChat() {
            taskId = crypto.randomUUID();
            chat.innerHTML = '<div class="msg system">New conversation started</div>';
            input.focus();
        }

        async function send() {
            const text = input.value.trim();
            if (!text) return;
            addMsg(text, 'user');
            input.value = '';
            btn.disabled = true;
            const loading = addMsg('Thinking', 'agent');
            loading.classList.add('loading');

            try {
                const res = await fetch('/tasks/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'x-api-key': '""" + config["agent_api_key"] + """' },
                    body: JSON.stringify({
                        jsonrpc: '2.0', id: crypto.randomUUID(), method: 'tasks/send',
                        params: { id: taskId, message: { role: 'user', parts: [{ type: 'text', text }] } }
                    })
                });
                const data = await res.json();
                loading.remove();
                if (data.result && data.result.artifacts) {
                    const reply = data.result.artifacts[0].parts[0].text;
                    const state = data.result.status.state;
                    const msgEl = addMsg(reply, 'agent');
                    const pill = document.createElement('div');
                    pill.className = 'status-pill ' + state;
                    pill.textContent = state;
                    msgEl.appendChild(pill);
                } else {
                    addMsg('Unexpected response', 'agent');
                }
            } catch (e) {
                loading.remove();
                addMsg('Error: ' + e.message, 'agent');
            }
            btn.disabled = false;
            input.focus();
        }

        function addMsg(text, type) {
            const div = document.createElement('div');
            div.className = 'msg ' + type;
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            return div;
        }
    </script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# CONFIG UI
# ═══════════════════════════════════════════════════════════════

CONFIG_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2A Agent — Configuration</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #08090a; color: #e0e0e0; min-height: 100vh; display: flex; justify-content: center; padding: 40px 20px; }}
        .container {{ max-width: 640px; width: 100%; }}
        .topbar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; }}
        .topbar a {{ color: #6366f1; text-decoration: none; font-size: 13px; font-weight: 500; }}
        .topbar h1 {{ font-size: 22px; font-weight: 700; color: #fff; }}
        .status-bar {{ display: flex; gap: 12px; margin-bottom: 24px; padding: 12px 16px; background: #111214; border: 1px solid #1e1f23; border-radius: 10px; }}
        .status-item {{ display: flex; align-items: center; gap: 6px; font-size: 13px; color: #aaa; }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; }}
        .dot.green {{ background: #22c55e; box-shadow: 0 0 6px #22c55e55; }}
        .dot.red {{ background: #ef4444; box-shadow: 0 0 6px #ef444455; }}
        .card {{ background: #111214; border: 1px solid #1e1f23; border-radius: 12px; padding: 24px; margin-bottom: 16px; }}
        .card h2 {{ font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 16px; }}
        .field {{ margin-bottom: 14px; }}
        .field label {{ display: block; font-size: 12px; font-weight: 500; color: #888; margin-bottom: 5px; }}
        .field input, .field select, .field textarea {{ width: 100%; padding: 10px 12px; background: #08090a; border: 1px solid #2a2b2e; border-radius: 8px; color: #fff; font-size: 14px; font-family: inherit; }}
        .field input:focus, .field select:focus, .field textarea:focus {{ outline: none; border-color: #6366f1; }}
        .field textarea {{ resize: vertical; min-height: 80px; }}
        .field .hint {{ font-size: 11px; color: #555; margin-top: 3px; }}
        .provider-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; }}
        .provider-option {{ padding: 10px; background: #08090a; border: 2px solid #2a2b2e; border-radius: 8px; text-align: center; cursor: pointer; transition: all 0.2s; }}
        .provider-option:hover {{ border-color: #444; }}
        .provider-option.selected {{ border-color: #6366f1; background: #13132a; }}
        .provider-option input {{ display: none; }}
        .provider-option .name {{ font-size: 13px; font-weight: 600; color: #fff; }}
        .provider-option .sub {{ font-size: 11px; color: #666; margin-top: 2px; }}
        .btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 11px 24px; font-size: 14px; font-weight: 600; border: none; border-radius: 8px; cursor: pointer; width: 100%; }}
        .btn-primary {{ background: #6366f1; color: #fff; }}
        .btn-primary:hover {{ background: #5558e6; }}
        .btn-test {{ background: transparent; color: #6366f1; border: 1px solid #6366f1; margin-top: 8px; }}
        .toast {{ position: fixed; bottom: 20px; right: 20px; padding: 12px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; display: none; z-index: 100; }}
        .toast.success {{ background: #052e16; border: 1px solid #22c55e44; color: #22c55e; display: block; }}
        .toast.error {{ background: #2a0a0a; border: 1px solid #ef444444; color: #ef4444; display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar"><a href="/console">&larr; Console</a><h1>Configuration</h1><span></span></div>
        <div class="status-bar">
            <div class="status-item"><div class="dot {llm_dot}"></div>LLM: {llm_status}</div>
            <div class="status-item"><div class="dot green"></div>Agent: Running</div>
        </div>
        <form method="POST" action="/config">
            <div class="card">
                <h2>LLM Provider</h2>
                <div class="provider-grid">
                    <label class="provider-option {anthropic_sel}"><input type="radio" name="llm_provider" value="anthropic" {anthropic_chk}><div class="name">Anthropic</div><div class="sub">Claude</div></label>
                    <label class="provider-option {openai_sel}"><input type="radio" name="llm_provider" value="openai" {openai_chk}><div class="name">OpenAI</div><div class="sub">GPT</div></label>
                    <label class="provider-option {google_sel}"><input type="radio" name="llm_provider" value="google" {google_chk}><div class="name">Google</div><div class="sub">Gemini</div></label>
                </div>
                <div class="field">
                    <label>API Key</label>
                    <input type="hidden" name="api_key_anthropic" id="api_key_anthropic" value="{api_key_anthropic}">
                    <input type="hidden" name="api_key_openai" id="api_key_openai" value="{api_key_openai}">
                    <input type="hidden" name="api_key_google" id="api_key_google" value="{api_key_google}">
                    <input type="password" id="visible_api_key" placeholder="Enter your LLM API key">
                    <div class="hint">Keys stored per provider — switching keeps your keys</div>
                </div>
                <div class="field">
                    <label>Model</label>
                    <select name="llm_model" id="model-select"><option value="">Select a model</option></select>
                </div>
            </div>
            <div class="card">
                <h2>Agent Settings</h2>
                <div class="field"><label>Agent Name</label><input type="text" name="agent_name" value="{agent_name}"></div>
                <div class="field"><label>A2A Auth Key</label><input type="text" name="agent_api_key" value="{agent_api_key}"><div class="hint">Clients use this to authenticate</div></div>
                <div class="field"><label>System Prompt</label><textarea name="system_prompt" rows="4">{system_prompt}</textarea></div>
            </div>
            <button type="submit" class="btn btn-primary">Save Configuration</button>
            <button type="button" class="btn btn-test" onclick="testLLM()">Test LLM Connection</button>
        </form>
    </div>
    <div id="toast" class="toast"></div>
    <script>
        document.querySelectorAll('.provider-option').forEach(o => {{
            o.addEventListener('click', () => {{
                saveVisibleKey();
                document.querySelectorAll('.provider-option').forEach(x => x.classList.remove('selected'));
                o.classList.add('selected');
                o.querySelector('input').checked = true;
                const prov = o.querySelector('input').value;
                updateModels(prov);
                loadKeyForProvider(prov);
            }});
        }});
        const models = {{ anthropic: ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"], openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"], google: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"] }};
        const currentModel = "{llm_model}";
        const currentProvider = document.querySelector('.provider-option.selected input')?.value || "anthropic";
        const visibleKey = document.getElementById('visible_api_key');
        function getActiveProvider() {{ return document.querySelector('.provider-option.selected input')?.value || "anthropic"; }}
        function loadKeyForProvider(prov) {{ const h = document.getElementById('api_key_' + prov); visibleKey.value = h ? h.value : ''; }}
        function saveVisibleKey() {{ const h = document.getElementById('api_key_' + getActiveProvider()); if (h) h.value = visibleKey.value; }}
        visibleKey.addEventListener('input', () => {{ saveVisibleKey(); }});
        document.querySelector('form').addEventListener('submit', () => {{ saveVisibleKey(); }});
        function updateModels(provider) {{ const sel = document.getElementById('model-select'); sel.innerHTML = ''; (models[provider] || []).forEach(m => {{ const opt = document.createElement('option'); opt.value = m; opt.textContent = m; if (m === currentModel) opt.selected = true; sel.appendChild(opt); }}); }}
        updateModels(currentProvider);
        loadKeyForProvider(currentProvider);
        const p = new URLSearchParams(location.search);
        if (p.get('saved')) showToast('Configuration saved!', 'success');
        function showToast(m, t) {{ const e = document.getElementById('toast'); e.textContent = m; e.className = 'toast ' + t; setTimeout(() => e.style.display = 'none', 3000); }}
        async function testLLM() {{
            const btn = document.querySelector('.btn-test');
            btn.textContent = 'Saving & Testing...';
            saveVisibleKey();
            const formData = new FormData(document.querySelector('form'));
            try {{
                await fetch('/config', {{ method: 'POST', body: formData }});
                const r = await fetch('/test-llm');
                const d = await r.json();
                showToast(d.success ? 'Connected! ' + d.response.substring(0, 60) : 'Failed: ' + d.error, d.success ? 'success' : 'error');
            }} catch(e) {{ showToast('Error: ' + e.message, 'error'); }}
            btn.textContent = 'Test LLM Connection';
        }}
    </script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/console", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def console_page(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" not in accept and request.url.path == "/":
        return HTMLResponse(content="")
    is_configured = bool(config["api_keys"].get(config["llm_provider"], ""))
    provider_name = PROVIDERS.get(config["llm_provider"], {}).get("name", config["llm_provider"])
    if is_configured:
        status_text, status_bg, status_border, status_color = f"Ready — {provider_name}", "#0a1a0a", "#22c55e33", "#22c55e"
    else:
        status_text, status_bg, status_border, status_color = "Setup required", "#1a0a0a", "#ef444433", "#ef4444"
    return HTMLResponse(content=CONSOLE_HTML.format(agent_name=config["agent_name"], provider_name=provider_name, service_url=SERVICE_URL, status_text=status_text, status_bg=status_bg, status_border=status_border, status_color=status_color))


@app.get("/config", response_class=HTMLResponse)
async def config_page():
    current_key = config["api_keys"].get(config["llm_provider"], "")
    is_configured = bool(current_key)
    return HTMLResponse(content=CONFIG_HTML.format(
        llm_dot="green" if is_configured else "red", llm_status="Connected" if is_configured else "Not configured",
        api_key_anthropic=config["api_keys"].get("anthropic", ""), api_key_openai=config["api_keys"].get("openai", ""), api_key_google=config["api_keys"].get("google", ""),
        llm_model=config["llm_model"], agent_name=config["agent_name"], agent_api_key=config["agent_api_key"], system_prompt=config["system_prompt"],
        anthropic_sel="selected" if config["llm_provider"] == "anthropic" else "", anthropic_chk="checked" if config["llm_provider"] == "anthropic" else "",
        openai_sel="selected" if config["llm_provider"] == "openai" else "", openai_chk="checked" if config["llm_provider"] == "openai" else "",
        google_sel="selected" if config["llm_provider"] == "google" else "", google_chk="checked" if config["llm_provider"] == "google" else "",
    ))


@app.post("/config")
async def save_config(llm_provider: str = Form(...), llm_model: str = Form(""), agent_name: str = Form("A2A Assistant"), agent_api_key: str = Form("test-key-change-me"), system_prompt: str = Form(""), api_key_anthropic: str = Form(""), api_key_openai: str = Form(""), api_key_google: str = Form("")):
    config["llm_provider"] = llm_provider
    config["llm_model"] = llm_model or PROVIDERS.get(llm_provider, {}).get("models", [""])[0]
    config["agent_name"] = agent_name
    config["agent_api_key"] = agent_api_key
    config["system_prompt"] = system_prompt
    config["api_keys"]["anthropic"] = api_key_anthropic
    config["api_keys"]["openai"] = api_key_openai
    config["api_keys"]["google"] = api_key_google
    return RedirectResponse(url="/config?saved=1", status_code=303)


@app.get("/playground", response_class=HTMLResponse)
async def playground_page():
    return HTMLResponse(content=PLAYGROUND_HTML)


@app.get("/test-llm")
async def test_llm():
    try:
        response = await call_llm([{"role": "user", "content": "Say hello in one sentence."}])
        clean, _ = parse_status(response)
        return {"success": True, "response": clean}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# MULTI-PROVIDER LLM
# ═══════════════════════════════════════════════════════════════

async def call_llm(messages: list[dict]) -> str:
    provider = config["llm_provider"]
    api_key = config["api_keys"].get(provider, "")
    model = config["llm_model"]
    system = config["system_prompt"]

    if not api_key:
        return f"⚙️ This agent hasn't been configured yet.\n\nPlease set it up at: {SERVICE_URL}/config\n\n[STATUS:completed]"

    async with httpx.AsyncClient(timeout=60.0) as client:
        if provider == "anthropic":
            resp = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json={"model": model, "max_tokens": 4096, "system": system, "messages": messages})
            if resp.status_code != 200:
                return f"LLM error ({resp.status_code}). Check API key at {SERVICE_URL}/config\n\n[STATUS:completed]"
            data = resp.json()
            return "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")

        elif provider == "openai":
            oai_messages = [{"role": "system", "content": system}] + messages
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "max_tokens": 4096, "messages": oai_messages})
            if resp.status_code != 200:
                return f"LLM error ({resp.status_code}). Check API key at {SERVICE_URL}/config\n\n[STATUS:completed]"
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        elif provider == "google":
            gemini_contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in messages]
            resp = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, json={"system_instruction": {"parts": [{"text": system}]}, "contents": gemini_contents})
            if resp.status_code != 200:
                return f"LLM error ({resp.status_code}). Check API key at {SERVICE_URL}/config\n\n[STATUS:completed]"
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    return f"Unknown provider.\n\n[STATUS:completed]"


# ═══════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    public_paths = ("/.well-known/agent.json", "/health", "/config", "/test-llm", "/console", "/playground")
    if request.url.path in public_paths:
        return await call_next(request)
    if request.url.path == "/" and request.method == "GET":
        return await call_next(request)
    api_key = (request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "").replace("bearer ", "") or request.headers.get("api-key") or request.headers.get("apikey"))
    if api_key != config["agent_api_key"]:
        return JSONResponse(status_code=401, content={"error": "Invalid or missing API key"})
    return await call_next(request)


# ═══════════════════════════════════════════════════════════════
# AGENT CARD
# ═══════════════════════════════════════════════════════════════

@app.get("/.well-known/agent.json")
async def agent_card():
    return {
        "name": config["agent_name"],
        "description": f"General-purpose AI assistant powered by {PROVIDERS.get(config['llm_provider'], {}).get('name', config['llm_provider'])}. Supports multi-turn conversations.",
        "url": SERVICE_URL, "version": "3.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": False},
        "skills": [{"id": "general-assistant", "name": "General Assistant", "description": "Multi-turn AI assistant — answers questions, writes code, drafts content, and more", "examples": ["Explain quantum computing simply", "Write a Python script to parse CSV", "Help me draft a professional email", "Compare REST vs GraphQL"]}],
        "authentication": {"schemes": ["apiKey"], "credentials": "API key via x-api-key header"},
    }


# ═══════════════════════════════════════════════════════════════
# A2A ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/")
async def root_post_handler(request: Request):
    return await _process_a2a_request(request)

@app.post("/tasks/send")
async def handle_task(request: Request):
    return await _process_a2a_request(request)

@app.post("/message/send")
async def handle_message(request: Request):
    return await _process_a2a_request(request)


async def _process_a2a_request(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    user_text = ""
    task_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    rpc_id = body.get("id", "1")

    if body.get("params"):
        params = body["params"]
        task_id = params.get("id", task_id)
        context_id = params.get("contextId", context_id)
        message = params.get("message", {})
        for part in message.get("parts", []):
            if "text" in part:
                user_text += part["text"]
    elif body.get("message"):
        message = body["message"]
        if isinstance(message, str):
            user_text = message
        elif isinstance(message, dict):
            for part in message.get("parts", []):
                if "text" in part:
                    user_text += part["text"]
            if not user_text:
                user_text = message.get("text", "")
    elif body.get("text"):
        user_text = body["text"]

    if not user_text:
        return _error_response(rpc_id, task_id, "No text content in message")

    # Get or create conversation history for this task
    if task_id not in conversations:
        conversations[task_id] = []

    # Add user message to history
    conversations[task_id].append({"role": "user", "content": user_text})

    # Call LLM with full conversation history
    raw_response = await call_llm(conversations[task_id])

    # Parse status from response
    clean_response, status = parse_status(raw_response)

    # Add assistant response to history
    conversations[task_id].append({"role": "assistant", "content": clean_response})

    # Clean up completed conversations (keep max 100 active)
    if status == "completed" and task_id in conversations:
        del conversations[task_id]
    if len(conversations) > 100:
        oldest = list(conversations.keys())[0]
        del conversations[oldest]

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "id": task_id,
            "contextId": context_id,
            "status": {"state": status},
            "artifacts": [{"parts": [{"type": "text", "text": clean_response}]}],
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": config["agent_name"],
        "provider": config["llm_provider"],
        "llm_configured": bool(config["api_keys"].get(config["llm_provider"], "")),
        "active_conversations": len(conversations),
    }


def _error_response(rpc_id, task_id, message, context_id=None):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": {"id": task_id, "contextId": context_id or str(uuid.uuid4()), "status": {"state": "failed", "message": {"role": "agent", "parts": [{"type": "text", "text": message}]}}}}
