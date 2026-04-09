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


def parse_status(text: str) -> tuple[str, TaskState]:
    """Extract status tag and return clean text + TaskState."""
    match = re.search(r'\[STATUS:(completed|input-required)\]\s*$', text)
    if match:
        status_str = match.group(1)
        clean = text[:match.start()].rstrip()
        if status_str == "completed":
            return clean, TaskState.completed
        else:
            return clean, TaskState.input_required
    return text, TaskState.completed


# ═══════════════════════════════════════════════════════════════
# MULTI-PROVIDER LLM AGENT
# ═══════════════════════════════════════════════════════════════

class LLMAgent:
    """Multi-provider LLM agent with conversation history."""

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "anthropic")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
        self.system_prompt = os.environ.get(
            "SYSTEM_PROMPT",
            "You are a helpful AI assistant. Be concise, accurate, and helpful.",
        )
        self.conversations: dict[str, list[dict]] = {}

    def _get_system(self) -> str:
        return self.system_prompt + STATUS_INSTRUCTION

    async def invoke(self, user_message: str, context_id: str = "") -> str:
        if not self.api_key:
            return "Agent not configured. Please visit /config to set up your LLM provider.\n\n[STATUS:input-required]"

        if context_id not in self.conversations:
            self.conversations[context_id] = []
        self.conversations[context_id].append({"role": "user", "content": user_message})
        messages = self.conversations[context_id]

        async with httpx.AsyncClient(timeout=60.0) as client:
            if self.provider == "anthropic":
                result = await self._call_anthropic(client, messages)
            elif self.provider == "openai":
                result = await self._call_openai(client, messages)
            elif self.provider == "google":
                result = await self._call_google(client, messages)
            else:
                result = "Unknown provider.\n\n[STATUS:completed]"

        clean_result, _ = parse_status(result)
        self.conversations[context_id].append({"role": "assistant", "content": clean_result})

        if len(self.conversations) > 100:
            oldest = next(iter(self.conversations))
            del self.conversations[oldest]

        return result

    def cleanup_context(self, context_id: str):
        self.conversations.pop(context_id, None)

    async def _call_anthropic(self, client: httpx.AsyncClient, messages: list[dict]) -> str:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 4096, "system": self._get_system(), "messages": messages},
        )
        if resp.status_code != 200:
            return f"Anthropic API error: {resp.status_code}\n\n[STATUS:completed]"
        data = resp.json()
        return "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")

    async def _call_openai(self, client: httpx.AsyncClient, messages: list[dict]) -> str:
        oai_messages = [{"role": "system", "content": self._get_system()}] + messages
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "max_tokens": 4096, "messages": oai_messages},
        )
        if resp.status_code != 200:
            return f"OpenAI API error: {resp.status_code}\n\n[STATUS:completed]"
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_google(self, client: httpx.AsyncClient, messages: list[dict]) -> str:
        gemini_contents = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json={"system_instruction": {"parts": [{"text": self._get_system()}]}, "contents": gemini_contents},
        )
        if resp.status_code != 200:
            return f"Google API error: {resp.status_code}\n\n[STATUS:completed]"
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


# ═══════════════════════════════════════════════════════════════
# A2A AGENT EXECUTOR (using TaskUpdater)
# ═══════════════════════════════════════════════════════════════

class LLMAgentExecutor(AgentExecutor):
    """A2A Agent Executor with multi-turn conversations and status signaling."""

    def __init__(self):
        self.agent = LLMAgent()

    @override
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        # Use TaskUpdater — handles taskId, contextId, events automatically
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # Signal task submitted and working
        updater.submit()
        updater.start_work()

        # Extract user message text
        user_text = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part, "root") and hasattr(part.root, "text"):
                    user_text += part.root.text
                elif hasattr(part, "text"):
                    user_text += part.text

        if not user_text:
            user_text = "Hello"

        # Call LLM with conversation history
        ctx_id = context.context_id or context.task_id
        raw_result = await self.agent.invoke(user_text, ctx_id)

        # Parse status signal
        clean_result, task_state = parse_status(raw_result)

        # Add artifact
        updater.add_artifact([TextPart(text=clean_result)], name="response")

        # Set final status
        updater.update_status(
            task_state,
            message=updater.new_agent_message(parts=[TextPart(text=clean_result)]),
        )

        # Clean up completed conversations
        if task_state == TaskState.completed:
            self.agent.cleanup_context(ctx_id)

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception("cancel not supported")
