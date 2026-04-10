import os
import re
import httpx
from typing_extensions import override
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, TextPart


# ═══════════════════════════════════════════════════════════════
# STATUS SIGNALING
# ═══════════════════════════════════════════════════════════════

STATUS_INSTRUCTION = """

SYSTEM REQUIREMENT — you MUST end every response with exactly one of these tags on its own line:
[STATUS:input-required]   ← USE THIS BY DEFAULT for every response
[STATUS:completed]         ← ONLY if the user explicitly says "bye", "goodbye", "thanks that's all", "done", or "no more questions"

The default is ALWAYS [STATUS:input-required]. Never skip the tag. It must be the very last line."""


def parse_status(text: str) -> tuple[str, TaskState]:
    # Try strict match first
    match = re.search(r'\[STATUS:(completed|input-required)\]', text, re.IGNORECASE)
    if match:
        clean = text[:match.start()].rstrip()
        # Remove any trailing content after the tag too
        return (clean, TaskState.completed) if "completed" in match.group(1).lower() else (clean, TaskState.input_required)
    
    # No tag found — default to input-required (safer, keeps conversation open)
    print(f"[DEBUG] No STATUS tag found in response, defaulting to input-required. Last 100 chars: {text[-100:]}")
    return text, TaskState.input_required


# ═══════════════════════════════════════════════════════════════
# PER-USER CONFIG STORE
# ═══════════════════════════════════════════════════════════════

# Shared store — main.py populates this, executor reads it
user_configs: dict[str, dict] = {}

DEFAULT_CONFIG = {
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-20250514",
    "system_prompt": "You are a helpful AI assistant. Be concise, accurate, and helpful.",
    "api_keys": {"anthropic": "", "openai": "", "google": ""},
}


def get_user_config(email: str) -> dict:
    if email not in user_configs:
        # Copy defaults
        user_configs[email] = {
            "llm_provider": DEFAULT_CONFIG["llm_provider"],
            "llm_model": DEFAULT_CONFIG["llm_model"],
            "system_prompt": DEFAULT_CONFIG["system_prompt"],
            "api_keys": dict(DEFAULT_CONFIG["api_keys"]),
        }
    return user_configs[email]


# ═══════════════════════════════════════════════════════════════
# MULTI-PROVIDER LLM
# ═══════════════════════════════════════════════════════════════

class LLMAgent:
    conversations: dict[str, list[dict]] = {}

    async def invoke(self, user_message: str, user_email: str, context_id: str = "") -> str:
        cfg = get_user_config(user_email)
        provider = cfg["llm_provider"]
        api_key = cfg["api_keys"].get(provider, "")
        model = cfg["llm_model"]
        system = cfg["system_prompt"] + STATUS_INSTRUCTION

        if not api_key:
            return f"Agent not configured for {user_email}. Please visit /config and set up your LLM provider.\n\n[STATUS:input-required]"

        # Conversation history
        conv_key = f"{user_email}:{context_id}"
        if conv_key not in self.conversations:
            self.conversations[conv_key] = []
        self.conversations[conv_key].append({"role": "user", "content": user_message})
        messages = self.conversations[conv_key]

        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "anthropic":
                result = await self._anthropic(client, api_key, model, system, messages)
            elif provider == "openai":
                result = await self._openai(client, api_key, model, system, messages)
            elif provider == "google":
                result = await self._google(client, api_key, model, system, messages)
            else:
                result = "Unknown provider.\n\n[STATUS:input-required]"

        clean, _ = parse_status(result)
        self.conversations[conv_key].append({"role": "assistant", "content": clean})

        if len(self.conversations) > 200:
            oldest = next(iter(self.conversations))
            del self.conversations[oldest]

        return result

    def cleanup(self, user_email: str, context_id: str):
        self.conversations.pop(f"{user_email}:{context_id}", None)

    async def _anthropic(self, client, key, model, system, msgs):
        r = await client.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 4096, "system": system, "messages": msgs})
        if r.status_code != 200: return f"Anthropic error: {r.status_code}\n\n[STATUS:input-required]"
        return "".join(b["text"] for b in r.json().get("content", []) if b.get("type") == "text")

    async def _openai(self, client, key, model, system, msgs):
        r = await client.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 4096, "messages": [{"role": "system", "content": system}] + msgs})
        if r.status_code != 200: return f"OpenAI error: {r.status_code}\n\n[STATUS:input-required]"
        return r.json()["choices"][0]["message"]["content"]

    async def _google(self, client, key, model, system, msgs):
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in msgs]
        r = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            json={"system_instruction": {"parts": [{"text": system}]}, "contents": contents})
        if r.status_code != 200: return f"Google error: {r.status_code}\n\n[STATUS:input-required]"
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


# ═══════════════════════════════════════════════════════════════
# A2A EXECUTOR
# ═══════════════════════════════════════════════════════════════

# This gets set by main.py's middleware after token validation
_current_user_email = ""


class LLMAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = LLMAgent()

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        global _current_user_email
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.submit()
        await updater.start_work()

        # Extract text
        user_text = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part, "root") and hasattr(part.root, "text"):
                    user_text += part.root.text
                elif hasattr(part, "text"):
                    user_text += part.text
        if not user_text:
            user_text = "Hello"

        # Use the authenticated user's email for config lookup
        email = _current_user_email or "default"
        ctx_id = context.context_id or context.task_id

        raw = await self.agent.invoke(user_text, email, ctx_id)
        print(f"[DEBUG] Raw LLM response (last 150 chars): ...{raw[-150:]}")
        clean, state = parse_status(raw)
        print(f"[DEBUG] Parsed state: {state}")

        await updater.add_artifact([TextPart(text=clean)], name="response")
        await updater.update_status(state, message=updater.new_agent_message(parts=[TextPart(text=clean)]))

        if state == TaskState.completed:
            self.agent.cleanup(email, ctx_id)

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")
