import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.routing import Route
from starlette.responses import HTMLResponse, RedirectResponse
from agent_executor import LLMAgentExecutor

SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:9999")
PORT = int(os.environ.get("PORT", "9999"))

# ═══════════════════════════════════════════════════════════════
# CONFIG STORE
# ═══════════════════════════════════════════════════════════════

config = {
    "llm_provider": os.environ.get("LLM_PROVIDER", "anthropic"),
    "llm_model": os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"),
    "agent_name": os.environ.get("AGENT_NAME", "A2A Assistant"),
    "system_prompt": os.environ.get("SYSTEM_PROMPT", "You are a helpful AI assistant. Be concise, accurate, and helpful."),
    "api_keys": {
        "anthropic": os.environ.get("LLM_API_KEY", "") if os.environ.get("LLM_PROVIDER", "anthropic") == "anthropic" else "",
        "openai": os.environ.get("LLM_API_KEY", "") if os.environ.get("LLM_PROVIDER", "") == "openai" else "",
        "google": os.environ.get("LLM_API_KEY", "") if os.environ.get("LLM_PROVIDER", "") == "google" else "",
    },
}

PROVIDERS = {
    "anthropic": {"name": "Anthropic (Claude)", "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]},
    "openai": {"name": "OpenAI (GPT)", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    "google": {"name": "Google (Gemini)", "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]},
}

# ═══════════════════════════════════════════════════════════════
# A2A SDK SETUP
# ═══════════════════════════════════════════════════════════════

skill = AgentSkill(
    id="general-assistant",
    name="General Assistant",
    description="AI-powered assistant that answers questions, writes code, drafts content, and more.",
    tags=["general", "coding", "writing", "analysis"],
    examples=["Explain quantum computing", "Write a Python sort function", "Draft a professional email", "Compare REST vs GraphQL"],
)

agent_card = AgentCard(
    name=config["agent_name"],
    description=f"General-purpose AI assistant powered by {config['llm_provider']}. Built with the official a2a-sdk.",
    url=f"{SERVICE_URL}/",
    version="3.0.0",
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


# ═══════════════════════════════════════════════════════════════
# HELPER: push config to executor
# ═══════════════════════════════════════════════════════════════

def _apply_config():
    executor.agent.provider = config["llm_provider"]
    executor.agent.api_key = config["api_keys"].get(config["llm_provider"], "")
    executor.agent.model = config["llm_model"]
    executor.agent.system_prompt = config["system_prompt"]


# ═══════════════════════════════════════════════════════════════
# HTML TEMPLATES
# ═══════════════════════════════════════════════════════════════

CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>A2A Agent Console</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh}.hero{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;padding:60px 20px 40px;text-align:center;background:radial-gradient(ellipse at 50% 0%,#1a1a3e 0%,#08090a 70%)}.logo{width:72px;height:72px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:36px;margin-bottom:24px;box-shadow:0 8px 32px #6366f133}.hero h1{font-size:36px;font-weight:800;color:#fff;margin-bottom:10px}.hero p{color:#888;font-size:16px;max-width:480px;line-height:1.5}.badge{display:inline-flex;align-items:center;gap:8px;margin-top:20px;padding:8px 16px;background:%%sbg%%;border:1px solid %%sbd%%;border-radius:20px;font-size:13px;font-weight:500;color:%%sc%%}.badge .dot{width:8px;height:8px;border-radius:50%;background:%%sc%%;box-shadow:0 0 6px %%sc%%55}.info{max-width:900px;margin:0 auto 24px;padding:0 20px}.info .inner{background:#111214;border:1px solid #1e1f23;border-radius:12px;padding:16px 20px;display:flex;align-items:center;gap:12px;font-size:13px;color:#888}.info .tag{background:#6366f122;color:#a5b4fc;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600}.info code{background:#1a1a1a;padding:2px 8px;border-radius:4px;color:#a5b4fc;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;max-width:900px;margin:0 auto;padding:0 20px 60px}.card{background:#111214;border:1px solid #1e1f23;border-radius:14px;padding:24px;transition:border .2s,transform .2s;text-decoration:none;color:inherit;display:block}.card:hover{border-color:#333;transform:translateY(-2px)}.card .icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:14px}.card .icon.purple{background:#6366f122}.card .icon.green{background:#22c55e22}.card .icon.orange{background:#f9731622}.card h3{font-size:15px;font-weight:600;color:#fff;margin-bottom:6px}.card p{font-size:13px;color:#777;line-height:1.4}</style></head><body>
<div class="hero"><div class="logo">⚡</div><h1>%%name%%</h1><p>A2A-compliant AI agent built with the official a2a-sdk. Powered by %%prov%%.</p><div class="badge"><div class="dot"></div>%%stxt%%</div></div>
<div class="info"><div class="inner"><span class="tag">A2A SDK</span><span>Agent URL: <code>%%url%%</code></span></div></div>
<div class="grid"><a href="/config" class="card"><div class="icon purple">⚙️</div><h3>Configuration</h3><p>Set up LLM provider, API keys, model, and system prompt.</p></a><a href="/.well-known/agent.json" class="card"><div class="icon green">📋</div><h3>Agent Card</h3><p>A2A agent card — served by the SDK.</p></a><a href="/playground" class="card"><div class="icon orange">🧪</div><h3>Playground</h3><p>Test your agent with live A2A messages.</p></a></div></body></html>"""

CONFIG_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Config</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh;display:flex;justify-content:center;padding:40px 20px}.c{max-width:640px;width:100%}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}.top a{color:#6366f1;text-decoration:none;font-size:13px;font-weight:500}.top h1{font-size:22px;font-weight:700;color:#fff}.sb{display:flex;gap:12px;margin-bottom:24px;padding:12px 16px;background:#111214;border:1px solid #1e1f23;border-radius:10px}.si{display:flex;align-items:center;gap:6px;font-size:13px;color:#aaa}.dot{width:8px;height:8px;border-radius:50%}.dot.g{background:#22c55e;box-shadow:0 0 6px #22c55e55}.dot.r{background:#ef4444;box-shadow:0 0 6px #ef444455}.cd{background:#111214;border:1px solid #1e1f23;border-radius:12px;padding:24px;margin-bottom:16px}.cd h2{font-size:15px;font-weight:600;color:#fff;margin-bottom:16px}.f{margin-bottom:14px}.f label{display:block;font-size:12px;font-weight:500;color:#888;margin-bottom:5px}.f input,.f select,.f textarea{width:100%;padding:10px 12px;background:#08090a;border:1px solid #2a2b2e;border-radius:8px;color:#fff;font-size:14px;font-family:inherit}.f input:focus,.f select:focus,.f textarea:focus{outline:none;border-color:#6366f1}.f textarea{resize:vertical;min-height:80px}.f .h{font-size:11px;color:#555;margin-top:3px}.pg{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}.po{padding:10px;background:#08090a;border:2px solid #2a2b2e;border-radius:8px;text-align:center;cursor:pointer;transition:all .2s}.po:hover{border-color:#444}.po.s{border-color:#6366f1;background:#13132a}.po input{display:none}.po .n{font-size:13px;font-weight:600;color:#fff}.po .sub{font-size:11px;color:#666;margin-top:2px}.btn{display:inline-flex;align-items:center;justify-content:center;padding:11px 24px;font-size:14px;font-weight:600;border:none;border-radius:8px;cursor:pointer;width:100%}.btn-p{background:#6366f1;color:#fff}.btn-p:hover{background:#5558e6}.toast{position:fixed;bottom:20px;right:20px;padding:12px 18px;border-radius:8px;font-size:13px;font-weight:500;display:none;z-index:100}.toast.ok{background:#052e16;border:1px solid #22c55e44;color:#22c55e;display:block}</style></head><body>
<div class="c"><div class="top"><a href="/console">&larr; Console</a><h1>Configuration</h1><span></span></div>
<div class="sb"><div class="si"><div class="dot %%ld%%"></div>LLM: %%ls%%</div><div class="si"><div class="dot g"></div>Agent: Running</div></div>
<form method="POST" action="/config"><div class="cd"><h2>LLM Provider</h2>
<div class="pg"><label class="po %%as%%"><input type="radio" name="llm_provider" value="anthropic" %%ac%%><div class="n">Anthropic</div><div class="sub">Claude</div></label><label class="po %%os%%"><input type="radio" name="llm_provider" value="openai" %%oc%%><div class="n">OpenAI</div><div class="sub">GPT</div></label><label class="po %%gs%%"><input type="radio" name="llm_provider" value="google" %%gc%%><div class="n">Google</div><div class="sub">Gemini</div></label></div>
<div class="f"><label>API Key</label><input type="hidden" name="api_key_anthropic" id="api_key_anthropic" value="%%ka%%"><input type="hidden" name="api_key_openai" id="api_key_openai" value="%%ko%%"><input type="hidden" name="api_key_google" id="api_key_google" value="%%kg%%"><input type="password" id="vk" placeholder="Enter your LLM API key"><div class="h">Keys stored per provider</div></div>
<div class="f"><label>Model</label><select name="llm_model" id="ms"><option>Select</option></select></div></div>
<div class="cd"><h2>Agent Settings</h2><div class="f"><label>Agent Name</label><input type="text" name="agent_name" value="%%an%%"></div><div class="f"><label>System Prompt</label><textarea name="system_prompt" rows="4">%%sp%%</textarea></div></div>
<button type="submit" class="btn btn-p">Save Configuration</button></form></div>
<div id="toast" class="toast"></div>
<script>
document.querySelectorAll('.po').forEach(o=>{o.addEventListener('click',()=>{sv();document.querySelectorAll('.po').forEach(x=>x.classList.remove('s'));o.classList.add('s');o.querySelector('input').checked=true;um(o.querySelector('input').value);lk(o.querySelector('input').value)})});
const models={anthropic:["claude-sonnet-4-20250514","claude-haiku-4-5-20251001"],openai:["gpt-4o","gpt-4o-mini","gpt-4-turbo"],google:["gemini-2.5-flash","gemini-2.0-flash","gemini-2.5-pro"]};
const cm="%%lm%%",cp=document.querySelector('.po.s input')?.value||"anthropic",vk=document.getElementById('vk');
function gp(){return document.querySelector('.po.s input')?.value||"anthropic"}
function lk(p){const h=document.getElementById('api_key_'+p);vk.value=h?h.value:''}
function sv(){const h=document.getElementById('api_key_'+gp());if(h)h.value=vk.value}
vk.addEventListener('input',()=>{sv()});document.querySelector('form').addEventListener('submit',()=>{sv()});
function um(p){const s=document.getElementById('ms');s.innerHTML='';(models[p]||[]).forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;if(m===cm)o.selected=true;s.appendChild(o)})}
um(cp);lk(cp);
const q=new URLSearchParams(location.search);if(q.get('saved')){const t=document.getElementById('toast');t.textContent='Configuration saved!';t.className='toast ok';setTimeout(()=>t.style.display='none',3000)}
</script></body></html>"""

PLAYGROUND_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Playground</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#08090a;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column}.top{padding:14px 24px;border-bottom:1px solid #1e1f23;display:flex;align-items:center;justify-content:space-between}.top a{color:#6366f1;text-decoration:none;font-size:13px;font-weight:500}.top h2{font-size:15px;font-weight:600;color:#fff}.chat{flex:1;max-width:720px;width:100%;margin:0 auto;padding:24px 20px;overflow-y:auto;display:flex;flex-direction:column;gap:16px}.msg{max-width:85%;padding:12px 16px;border-radius:14px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word}.msg.u{align-self:flex-end;background:#6366f1;color:#fff;border-bottom-right-radius:4px}.msg.a{align-self:flex-start;background:#1a1b1e;border:1px solid #2a2b2e;color:#ddd;border-bottom-left-radius:4px}.msg.s{align-self:center;color:#666;font-size:12px}.ib{padding:16px 20px;border-top:1px solid #1e1f23;max-width:720px;width:100%;margin:0 auto;display:flex;gap:10px}.ib input{flex:1;padding:12px 16px;background:#111214;border:1px solid #2a2b2e;border-radius:10px;color:#fff;font-size:14px}.ib input:focus{outline:none;border-color:#6366f1}.ib button{padding:12px 20px;background:#6366f1;color:#fff;border:none;border-radius:10px;font-weight:600;font-size:14px;cursor:pointer}.ib button:disabled{opacity:.5}.loading::after{content:'...';animation:d 1.2s steps(3,end) infinite}@keyframes d{0%{content:'.'}33%{content:'..'}66%{content:'...'}}</style></head><body>
<div class="top"><a href="/console">&larr; Console</a><h2>Agent Playground</h2><span></span></div>
<div class="chat" id="chat"><div class="msg s">Send a message to test your A2A agent (official SDK)</div></div>
<div class="ib"><input type="text" id="inp" placeholder="Type a message..." autofocus><button id="btn" onclick="go()">Send</button></div>
<script>
const chat=document.getElementById('chat'),inp=document.getElementById('inp'),btn=document.getElementById('btn');
inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&!btn.disabled)go()});
async function go(){
const t=inp.value.trim();if(!t)return;add(t,'u');inp.value='';btn.disabled=true;
const l=add('Thinking','a');l.classList.add('loading');
try{
const r=await fetch('/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:crypto.randomUUID(),method:'message/send',params:{message:{role:'user',parts:[{type:'text',text:t}],messageId:crypto.randomUUID()}}})});
const d=await r.json();l.remove();
if(d.result){const parts=d.result.artifacts?.[0]?.parts||d.result.status?.message?.parts||[];const txt=parts.map(p=>p.text||'').join('')||JSON.stringify(d.result);add(txt,'a')}
else if(d.error){add('Error: '+d.error.message,'a')}
else{add(JSON.stringify(d),'a')}
}catch(e){l.remove();add('Error: '+e.message,'a')}
btn.disabled=false;inp.focus()}
function add(t,c){const d=document.createElement('div');d.className='msg '+c;d.textContent=t;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d}
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# ═══════════════════════════════════════════════════════════════

async def console_handler(request):
    is_ok = bool(config["api_keys"].get(config["llm_provider"], ""))
    prov = PROVIDERS.get(config["llm_provider"], {}).get("name", config["llm_provider"])
    stxt = f"Ready — {prov}" if is_ok else "Setup required"
    sbg = "#0a1a0a" if is_ok else "#1a0a0a"
    sbd = "#22c55e33" if is_ok else "#ef444433"
    sc = "#22c55e" if is_ok else "#ef4444"
    html = CONSOLE_HTML.replace("%%name%%", config["agent_name"]).replace("%%prov%%", prov).replace("%%url%%", SERVICE_URL).replace("%%stxt%%", stxt).replace("%%sbg%%", sbg).replace("%%sbd%%", sbd).replace("%%sc%%", sc)
    return HTMLResponse(html)


async def config_get_handler(request):
    ck = config["api_keys"].get(config["llm_provider"], "")
    p = config["llm_provider"]
    html = CONFIG_HTML.replace("%%ld%%", "g" if ck else "r").replace("%%ls%%", "Connected" if ck else "Not configured")
    html = html.replace("%%ka%%", config["api_keys"].get("anthropic", "")).replace("%%ko%%", config["api_keys"].get("openai", "")).replace("%%kg%%", config["api_keys"].get("google", ""))
    html = html.replace("%%lm%%", config["llm_model"]).replace("%%an%%", config["agent_name"]).replace("%%sp%%", config["system_prompt"])
    html = html.replace("%%as%%", "s" if p == "anthropic" else "").replace("%%ac%%", "checked" if p == "anthropic" else "")
    html = html.replace("%%os%%", "s" if p == "openai" else "").replace("%%oc%%", "checked" if p == "openai" else "")
    html = html.replace("%%gs%%", "s" if p == "google" else "").replace("%%gc%%", "checked" if p == "google" else "")
    return HTMLResponse(html)


async def config_post_handler(request):
    form = await request.form()
    config["llm_provider"] = form.get("llm_provider", "anthropic")
    config["llm_model"] = form.get("llm_model", "") or PROVIDERS.get(config["llm_provider"], {}).get("models", [""])[0]
    config["agent_name"] = form.get("agent_name", "A2A Assistant")
    config["system_prompt"] = form.get("system_prompt", "")
    config["api_keys"]["anthropic"] = form.get("api_key_anthropic", "")
    config["api_keys"]["openai"] = form.get("api_key_openai", "")
    config["api_keys"]["google"] = form.get("api_key_google", "")
    _apply_config()
    return RedirectResponse(url="/config?saved=1", status_code=303)


async def playground_handler(request):
    return HTMLResponse(PLAYGROUND_HTML)


# Mount custom routes on top of SDK app
app.routes.insert(0, Route("/console", console_handler, methods=["GET"]))
app.routes.insert(0, Route("/config", config_get_handler, methods=["GET"]))
app.routes.insert(0, Route("/config", config_post_handler, methods=["POST"]))
app.routes.insert(0, Route("/playground", playground_handler, methods=["GET"]))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
