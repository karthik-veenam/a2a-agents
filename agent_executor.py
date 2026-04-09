import os
import httpx
from typing_extensions import override
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message


class LLMAgent:
    """Multi-provider LLM agent."""

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "anthropic")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
        self.system_prompt = os.environ.get(
            "SYSTEM_PROMPT",
            "You are a helpful AI assistant. Be concise, accurate, and helpful.",
        )

    async def invoke(self, user_message: str) -> str:
        if not self.api_key:
            return "Agent not configured. Please set LLM_API_KEY environment variable."

        async with httpx.AsyncClient(timeout=60.0) as client:
            if self.provider == "anthropic":
                return await self._call_anthropic(client, user_message)
            elif self.provider == "openai":
                return await self._call_openai(client, user_message)
            elif self.provider == "google":
                return await self._call_google(client, user_message)
        return "Unknown provider."

    async def _call_anthropic(self, client: httpx.AsyncClient, message: str) -> str:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "system": self.system_prompt,
                "messages": [{"role": "user", "content": message}],
            },
        )
        if resp.status_code != 200:
            return f"Anthropic API error: {resp.status_code}"
        data = resp.json()
        return "".join(
            b["text"] for b in data.get("content", []) if b.get("type") == "text"
        )

    async def _call_openai(self, client: httpx.AsyncClient, message: str) -> str:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message},
                ],
            },
        )
        if resp.status_code != 200:
            return f"OpenAI API error: {resp.status_code}"
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_google(self, client: httpx.AsyncClient, message: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        resp = await client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json={
                "system_instruction": {"parts": [{"text": self.system_prompt}]},
                "contents": [{"parts": [{"text": message}]}],
            },
        )
        if resp.status_code != 200:
            return f"Google API error: {resp.status_code}"
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


class LLMAgentExecutor(AgentExecutor):
    """A2A Agent Executor that routes requests to an LLM."""

    def __init__(self):
        self.agent = LLMAgent()

    @override
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
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

        # Call LLM
        result = await self.agent.invoke(user_text)

        # Send response back via event queue
        await event_queue.enqueue_event(new_agent_text_message(result))

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception("cancel not supported")
