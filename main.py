import os
import json
import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.routing import Route
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from agent_executor import LLMAgentExecutor, user_configs, get_user_config, DEFAULT_CONFIG
import agent_executor as ae

SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:9999")
PORT = int(os.environ.get("PORT", "9999"))

PROVIDERS = {
    "anthropic": {"name": "Anthropic (Claude)", "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]},
    "openai": {"name": "OpenAI (GPT)", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    "google": {"name": "Google (Gemini)", "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]},
}


# ═══════════════════════════════════════════════════════════════
# GOOGLE TOKEN VALIDATION
# ═══════════════════════════════════════════════════════════════

async def validate_google_token(token: str) -> dict | None:
    """Validate Google OAuth token and return user info (email, name)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try tokeninfo endpoint first (works for access tokens)
        r = await client.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")
        if r.status_code == 200:
            data = r.json()
            if data.get("email"):
                return {"email": data["email"], "name": data.get("name", data["email"])}

        # Try userinfo endpoint (works for OAuth access tokens)
        r = await client.get("https://www.googleapis.com/oauth2/v3/userinfo",
                             headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            data = r.json()
            if data.get("email"):
                return {"email": data["email"], "name": data.get("name", data["email"])}

    return None


# ═══════════════════════════════════════════════════════════════
# A2A SDK SETUP
# ═══════════════════════════════════════════════════════════════

skill = AgentSkill(
    id="general-assistant",
    name="General Assistant",
    description="AI-powered assistant — answers questions, writes code, drafts content, and more. Per-user config via Google OAuth.",
    tags=["general", "coding", "writing", "analysis"],
    examples=["Explain quantum computing", "Write a Python sort function", "Draft a professional email"],
)

agent_card = AgentCard(
    name="A2A Assistant",
    description="General-purpose AI assistant with per-user configuration. Authenticate with Google OAuth Bearer token.",
    url=f"{SERVICE_URL}/",
    version="4.0.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[skill],
)

executor = LLMAgentExecutor()

request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
)

app_builder = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

app = app_builder.build()

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════════════════════════════
# AUTH MIDDLEWARE — validates Google OAuth on A2A endpoints
# ═══════════════════════════════════════════════════════════════

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class GoogleOAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {"/.well-known/agent.json", "/console", "/config", "/playground", "/health",
                    "/api/config", "/api/config/load"}

    async def dispatch(self, request: Request, call_next):
        # OPTIONS for CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        # Public paths — no auth
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # GET on root = console page
        if request.url.path == "/" and request.method == "GET":
            return await call_next(request)

        # A2A endpoints need Bearer token
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"error": "Missing Bearer token. Authenticate with Google OAuth."})

        token = auth.replace("Bearer ", "")
        user = await validate_google_token(token)
        if not user:
            return JSONResponse(status_code=401, content={"error": "Invalid Google OAuth token."})

        # Set current user email for the executor
        ae._current_user_email = user["email"]

        response = await call_next(request)
        return response

app.add_middleware(GoogleOAuthMiddleware)


# ═══════════════════════════════════════════════════════════════
# HTML TEMPLATES
# ═══════════════════════════════════════════════════════════════

CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>A2A Agent Console</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh}.hero{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;padding:60px 20px 40px;text-align:center;background:radial-gradient(ellipse at 50% 0%,#1a1a3e 0%,#08090a 70%)}.logo{width:72px;height:72px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:36px;margin-bottom:24px;box-shadow:0 8px 32px #6366f133}.hero h1{font-size:36px;font-weight:800;color:#fff;margin-bottom:10px}.hero p{color:#888;font-size:16px;max-width:520px;line-height:1.5}.badge{display:inline-flex;align-items:center;gap:8px;margin-top:20px;padding:8px 16px;background:#0a1a0a;border:1px solid #22c55e33;border-radius:20px;font-size:13px;font-weight:500;color:#22c55e}.badge .dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 6px #22c55e55}.info{max-width:900px;margin:0 auto 24px;padding:0 20px}.info .inner{background:#111214;border:1px solid #1e1f23;border-radius:12px;padding:16px 20px;display:flex;align-items:center;gap:12px;font-size:13px;color:#888;flex-wrap:wrap}.info .tag{background:#6366f122;color:#a5b4fc;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600}.info code{background:#1a1a1a;padding:2px 8px;border-radius:4px;color:#a5b4fc;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;max-width:900px;margin:0 auto;padding:0 20px 60px}.card{background:#111214;border:1px solid #1e1f23;border-radius:14px;padding:24px;transition:border .2s,transform .2s;text-decoration:none;color:inherit;display:block}.card:hover{border-color:#333;transform:translateY(-2px)}.card .icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:14px}.card .icon.purple{background:#6366f122}.card .icon.green{background:#22c55e22}.card .icon.orange{background:#f9731622}.card .icon.blue{background:#3b82f622}.card h3{font-size:15px;font-weight:600;color:#fff;margin-bottom:6px}.card p{font-size:13px;color:#777;line-height:1.4}</style></head><body>
<div class="hero"><div class="logo">⚡</div><h1>A2A Assistant</h1><p>Multi-user A2A agent with Google OAuth authentication. Each user gets their own LLM configuration.</p><div class="badge"><div class="dot"></div>Running — OAuth + Per-user Config</div></div>
<div class="info"><div class="inner"><span class="tag">A2A SDK</span><span>URL: <code>%%url%%</code></span><span class="tag">OAuth</span><span>Auth: Google Bearer Token</span></div></div>
<div class="grid">
<a href="/config" class="card"><div class="icon purple">⚙️</div><h3>Configuration</h3><p>Enter your email to configure your personal LLM settings (provider, API key, model).</p></a>
<a href="/.well-known/agent.json" class="card"><div class="icon green">📋</div><h3>Agent Card</h3><p>A2A agent card with Bearer auth scheme.</p></a>
<a href="/playground" class="card"><div class="icon orange">🧪</div><h3>Playground</h3><p>Test the agent with your Google OAuth token.</p></a>
</div></body></html>"""

CONFIG_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Config</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh;display:flex;justify-content:center;padding:40px 20px}.c{max-width:640px;width:100%}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}.top a{color:#6366f1;text-decoration:none;font-size:13px;font-weight:500}.top h1{font-size:22px;font-weight:700;color:#fff}.sb{display:flex;gap:12px;margin-bottom:24px;padding:12px 16px;background:#111214;border:1px solid #1e1f23;border-radius:10px;flex-wrap:wrap}.si{display:flex;align-items:center;gap:6px;font-size:13px;color:#aaa}.dot{width:8px;height:8px;border-radius:50%}.dot.g{background:#22c55e;box-shadow:0 0 6px #22c55e55}.dot.r{background:#ef4444;box-shadow:0 0 6px #ef444455}.dot.y{background:#eab308;box-shadow:0 0 6px #eab30855}.cd{background:#111214;border:1px solid #1e1f23;border-radius:12px;padding:24px;margin-bottom:16px}.cd h2{font-size:15px;font-weight:600;color:#fff;margin-bottom:16px}.f{margin-bottom:14px}.f label{display:block;font-size:12px;font-weight:500;color:#888;margin-bottom:5px}.f input,.f select,.f textarea{width:100%;padding:10px 12px;background:#08090a;border:1px solid #2a2b2e;border-radius:8px;color:#fff;font-size:14px;font-family:inherit}.f input:focus,.f select:focus,.f textarea:focus{outline:none;border-color:#6366f1}.f textarea{resize:vertical;min-height:80px}.f .h{font-size:11px;color:#555;margin-top:3px}.pg{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}.po{padding:10px;background:#08090a;border:2px solid #2a2b2e;border-radius:8px;text-align:center;cursor:pointer;transition:all .2s}.po:hover{border-color:#444}.po.s{border-color:#6366f1;background:#13132a}.po input{display:none}.po .n{font-size:13px;font-weight:600;color:#fff}.po .sub{font-size:11px;color:#666;margin-top:2px}.btn{display:inline-flex;align-items:center;justify-content:center;padding:11px 24px;font-size:14px;font-weight:600;border:none;border-radius:8px;cursor:pointer;width:100%}.btn-p{background:#6366f1;color:#fff}.btn-p:hover{background:#5558e6}.btn-s{background:transparent;color:#6366f1;border:1px solid #6366f1;margin-top:8px}.btn-s:hover{background:#6366f111}.toast{position:fixed;bottom:20px;right:20px;padding:12px 18px;border-radius:8px;font-size:13px;font-weight:500;display:none;z-index:100}.toast.ok{background:#052e16;border:1px solid #22c55e44;color:#22c55e;display:block}.toast.err{background:#2a0a0a;border:1px solid #ef444444;color:#ef4444;display:block}.email-bar{display:flex;gap:8px;margin-bottom:20px}.email-bar input{flex:1}.email-bar button{padding:10px 20px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-weight:600;cursor:pointer;white-space:nowrap}.config-form{display:none}</style></head><body>
<div class="c">
<div class="top"><a href="/console">&larr; Console</a><h1>Configuration</h1><span></span></div>
<div class="cd"><h2>Your Identity</h2>
<div class="email-bar"><input type="email" id="email" placeholder="Enter your email to load config"><button onclick="loadConfig()">Load Config</button></div>
<div class="h" style="color:#666;font-size:12px">This email is used to store your personal LLM configuration. Same email the Google OAuth token resolves to.</div>
</div>
<div class="config-form" id="configForm">
<div class="sb"><div class="si"><div class="dot" id="statusDot"></div><span id="statusText">Loading...</span></div><div class="si" id="userLabel"></div></div>
<div class="cd"><h2>LLM Provider</h2>
<div class="pg"><label class="po" data-p="anthropic"><input type="radio" name="llm_provider" value="anthropic"><div class="n">Anthropic</div><div class="sub">Claude</div></label><label class="po" data-p="openai"><input type="radio" name="llm_provider" value="openai"><div class="n">OpenAI</div><div class="sub">GPT</div></label><label class="po" data-p="google"><input type="radio" name="llm_provider" value="google"><div class="n">Google</div><div class="sub">Gemini</div></label></div>
<div class="f"><label>API Key</label><input type="hidden" id="ak_anthropic"><input type="hidden" id="ak_openai"><input type="hidden" id="ak_google"><input type="password" id="vk" placeholder="Enter your LLM API key"><div class="h">Keys stored per provider, per user</div></div>
<div class="f"><label>Model</label><select id="ms"></select></div></div>
<div class="cd"><h2>Agent Settings</h2>
<div class="f"><label>System Prompt</label><textarea id="sp" rows="4"></textarea></div></div>
<button class="btn btn-p" onclick="saveConfig()">Save Configuration</button>
</div></div>
<div id="toast" class="toast"></div>
<script>
const models={anthropic:["claude-sonnet-4-20250514","claude-haiku-4-5-20251001"],openai:["gpt-4o","gpt-4o-mini","gpt-4-turbo"],google:["gemini-2.5-flash","gemini-2.0-flash","gemini-2.5-pro"]};
let currentEmail='';

document.querySelectorAll('.po').forEach(o=>{o.addEventListener('click',()=>{svk();document.querySelectorAll('.po').forEach(x=>x.classList.remove('s'));o.classList.add('s');o.querySelector('input').checked=true;um(o.dataset.p);ldk(o.dataset.p)})});

function gp(){return document.querySelector('.po.s input')?.value||'anthropic'}
function ldk(p){document.getElementById('vk').value=document.getElementById('ak_'+p)?.value||''}
function svk(){const h=document.getElementById('ak_'+gp());if(h)h.value=document.getElementById('vk').value}
document.getElementById('vk').addEventListener('input',()=>{svk()});
function um(p){const s=document.getElementById('ms');const cur=s.value;s.innerHTML='';(models[p]||[]).forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;s.appendChild(o)});if(cur)s.value=cur}

async function loadConfig(){
    const email=document.getElementById('email').value.trim();
    if(!email){toast('Enter your email','err');return}
    currentEmail=email;
    try{
        const r=await fetch('/api/config/load?email='+encodeURIComponent(email));
        const d=await r.json();
        // Set provider
        document.querySelectorAll('.po').forEach(o=>o.classList.remove('s'));
        const sel=document.querySelector('[data-p="'+d.llm_provider+'"]');
        if(sel){sel.classList.add('s');sel.querySelector('input').checked=true}
        // Set keys
        document.getElementById('ak_anthropic').value=d.api_keys?.anthropic||'';
        document.getElementById('ak_openai').value=d.api_keys?.openai||'';
        document.getElementById('ak_google').value=d.api_keys?.google||'';
        ldk(d.llm_provider);
        um(d.llm_provider);
        document.getElementById('ms').value=d.llm_model;
        document.getElementById('sp').value=d.system_prompt;
        // Status
        const hasKey=d.api_keys?.[d.llm_provider];
        document.getElementById('statusDot').className='dot '+(hasKey?'g':'r');
        document.getElementById('statusText').textContent=hasKey?'LLM: Connected':'LLM: Not configured';
        document.getElementById('userLabel').textContent='User: '+email;
        document.getElementById('configForm').style.display='block';
        toast('Config loaded for '+email,'ok');
    }catch(e){toast('Error loading config','err')}
}

async function saveConfig(){
    svk();
    const data={
        email:currentEmail,
        llm_provider:gp(),
        llm_model:document.getElementById('ms').value,
        system_prompt:document.getElementById('sp').value,
        api_keys:{
            anthropic:document.getElementById('ak_anthropic').value,
            openai:document.getElementById('ak_openai').value,
            google:document.getElementById('ak_google').value
        }
    };
    try{
        const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
        if(r.ok){
            toast('Configuration saved!','ok');
            const hasKey=data.api_keys[data.llm_provider];
            document.getElementById('statusDot').className='dot '+(hasKey?'g':'r');
            document.getElementById('statusText').textContent=hasKey?'LLM: Connected':'LLM: Not configured';
        }else{toast('Save failed','err')}
    }catch(e){toast('Error saving','err')}
}

function toast(m,t){const e=document.getElementById('toast');e.textContent=m;e.className='toast '+t;setTimeout(()=>e.style.display='none',3000)}
</script></body></html>"""

PLAYGROUND_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Playground</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column}.top{padding:14px 24px;border-bottom:1px solid #1e1f23;display:flex;align-items:center;justify-content:space-between}.top a{color:#6366f1;text-decoration:none;font-size:13px;font-weight:500}.top h2{font-size:15px;font-weight:600;color:#fff}.auth-bar{padding:12px 24px;background:#111214;border-bottom:1px solid #1e1f23;display:flex;gap:8px;align-items:center}.auth-bar input{flex:1;padding:8px 12px;background:#08090a;border:1px solid #2a2b2e;border-radius:8px;color:#fff;font-size:13px;font-family:monospace}.auth-bar button{padding:8px 16px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-weight:600;font-size:13px;cursor:pointer}.auth-bar .label{font-size:12px;color:#888;white-space:nowrap}.chat{flex:1;max-width:720px;width:100%;margin:0 auto;padding:24px 20px;overflow-y:auto;display:flex;flex-direction:column;gap:16px}.msg{max-width:85%;padding:12px 16px;border-radius:14px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word}.msg.u{align-self:flex-end;background:#6366f1;color:#fff;border-bottom-right-radius:4px}.msg.a{align-self:flex-start;background:#1a1b1e;border:1px solid #2a2b2e;color:#ddd;border-bottom-left-radius:4px}.msg.s{align-self:center;color:#666;font-size:12px}.ib{padding:16px 20px;border-top:1px solid #1e1f23;max-width:720px;width:100%;margin:0 auto;display:flex;gap:10px}.ib input{flex:1;padding:12px 16px;background:#111214;border:1px solid #2a2b2e;border-radius:10px;color:#fff;font-size:14px}.ib input:focus{outline:none;border-color:#6366f1}.ib button{padding:12px 20px;background:#6366f1;color:#fff;border:none;border-radius:10px;font-weight:600;font-size:14px;cursor:pointer}.ib button:disabled{opacity:.5}.loading::after{content:'...';animation:d 1.2s steps(3,end) infinite}@keyframes d{0%{content:'.'}33%{content:'..'}66%{content:'...'}}</style></head><body>
<div class="top"><a href="/console">&larr; Console</a><h2>Agent Playground</h2><span></span></div>
<div class="auth-bar"><span class="label">Bearer Token:</span><input type="text" id="token" placeholder="Paste your Google OAuth token here"><button onclick="setToken()">Set</button></div>
<div class="chat" id="chat"><div class="msg s">Paste your Google OAuth Bearer token above, then send a message.</div></div>
<div class="ib"><input type="text" id="inp" placeholder="Type a message..." autofocus><button id="btn" onclick="go()">Send</button></div>
<script>
const chat=document.getElementById('chat'),inp=document.getElementById('inp'),btn=document.getElementById('btn');
let bearerToken='';
function setToken(){bearerToken=document.getElementById('token').value.trim();if(bearerToken)add('Token set. You can now send messages.','s');else add('Please enter a token.','s')}
inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&!btn.disabled)go()});
async function go(){
if(!bearerToken){add('Set your Bearer token first.','s');return}
const t=inp.value.trim();if(!t)return;add(t,'u');inp.value='';btn.disabled=true;
const l=add('Thinking','a');l.classList.add('loading');
try{
const r=await fetch('/',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+bearerToken},body:JSON.stringify({jsonrpc:'2.0',id:crypto.randomUUID(),method:'message/send',params:{message:{role:'user',parts:[{type:'text',text:t}],messageId:crypto.randomUUID()}}})});
const d=await r.json();l.remove();
if(d.result){const parts=d.result.artifacts?.[0]?.parts||d.result.status?.message?.parts||[];const txt=parts.map(p=>p.text||'').join('')||JSON.stringify(d.result);add(txt,'a')}
else if(d.error){add('Error: '+(d.error.message||JSON.stringify(d.error)),'a')}
else{add(JSON.stringify(d),'a')}
}catch(e){l.remove();add('Error: '+e.message,'a')}
btn.disabled=false;inp.focus()}
function add(t,c){const d=document.createElement('div');d.className='msg '+c;d.textContent=t;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d}
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# ═══════════════════════════════════════════════════════════════

async def console_handler(request):
    html = CONSOLE_HTML.replace("%%url%%", SERVICE_URL)
    return HTMLResponse(html)


async def config_page_handler(request):
    return HTMLResponse(CONFIG_HTML)


async def config_load_handler(request):
    """API: Load config for a given email."""
    email = request.query_params.get("email", "")
    if not email:
        return JSONResponse({"error": "email required"}, status_code=400)
    cfg = get_user_config(email)
    return JSONResponse(cfg)


async def config_save_handler(request):
    """API: Save config for a given email."""
    data = await request.json()
    email = data.get("email", "")
    if not email:
        return JSONResponse({"error": "email required"}, status_code=400)

    cfg = get_user_config(email)
    cfg["llm_provider"] = data.get("llm_provider", cfg["llm_provider"])
    cfg["llm_model"] = data.get("llm_model", cfg["llm_model"])
    cfg["system_prompt"] = data.get("system_prompt", cfg["system_prompt"])
    if "api_keys" in data:
        cfg["api_keys"]["anthropic"] = data["api_keys"].get("anthropic", cfg["api_keys"]["anthropic"])
        cfg["api_keys"]["openai"] = data["api_keys"].get("openai", cfg["api_keys"]["openai"])
        cfg["api_keys"]["google"] = data["api_keys"].get("google", cfg["api_keys"]["google"])

    return JSONResponse({"status": "saved", "email": email})


async def playground_handler(request):
    return HTMLResponse(PLAYGROUND_HTML)


async def users_handler(request):
    """API: List configured users (for admin/debug)."""
    users = []
    for email, cfg in user_configs.items():
        has_key = bool(cfg["api_keys"].get(cfg["llm_provider"], ""))
        users.append({"email": email, "provider": cfg["llm_provider"], "configured": has_key})
    return JSONResponse({"users": users})


# Mount routes
app.routes.insert(0, Route("/console", console_handler, methods=["GET"]))
app.routes.insert(0, Route("/config", config_page_handler, methods=["GET"]))
app.routes.insert(0, Route("/api/config/load", config_load_handler, methods=["GET"]))
app.routes.insert(0, Route("/api/config", config_save_handler, methods=["POST"]))
app.routes.insert(0, Route("/playground", playground_handler, methods=["GET"]))
app.routes.insert(0, Route("/api/users", users_handler, methods=["GET"]))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
