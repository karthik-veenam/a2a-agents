import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent_executor import LLMAgentExecutor


SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:9999")
PORT = int(os.environ.get("PORT", "9999"))


# Define agent skills
skill = AgentSkill(
    id="general-assistant",
    name="General Assistant",
    description="AI-powered general assistant that can answer questions, write code, draft content, and help with any task.",
    tags=["general", "coding", "writing", "analysis", "math"],
    examples=[
        "Explain quantum computing in simple terms",
        "Write a Python function to sort a list",
        "Help me draft a professional email",
        "Compare REST vs GraphQL",
        "What are the pros and cons of microservices?",
    ],
)

# Define agent card
agent_name = os.environ.get("AGENT_NAME", "A2A Assistant")
llm_provider = os.environ.get("LLM_PROVIDER", "anthropic")

agent_card = AgentCard(
    name=agent_name,
    description=f"General-purpose AI assistant powered by {llm_provider}. Answers any question via the A2A protocol.",
    url=f"{SERVICE_URL}/",
    version="3.0.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[skill],
)

# Set up request handler with task store
request_handler = DefaultRequestHandler(
    agent_executor=LLMAgentExecutor(),
    task_store=InMemoryTaskStore(),
)

# Build the A2A application
app_builder = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

app = app_builder.build()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
