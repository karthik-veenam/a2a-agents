# A2A Agent (Official SDK)

General-purpose AI assistant exposed via the A2A protocol using the official `a2a-sdk`.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | No | `anthropic` | LLM provider: `anthropic`, `openai`, or `google` |
| `LLM_API_KEY` | Yes | - | API key for the chosen LLM provider |
| `LLM_MODEL` | No | `claude-sonnet-4-20250514` | Model ID |
| `SYSTEM_PROMPT` | No | (default) | Custom system prompt |
| `AGENT_NAME` | No | `A2A Assistant` | Agent display name |
| `SERVICE_URL` | Yes | `http://localhost:9999` | Public URL of the deployed agent |
| `PORT` | No | `9999` | Port to listen on |

## Local Development

```bash
pip install -r requirements.txt
LLM_API_KEY=your-key-here python main.py
```

## Deploy to Render

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Set env vars in Render dashboard

## Endpoints (handled by a2a-sdk)

- `GET /.well-known/agent.json` — Agent card
- `POST /` — A2A message/send (JSON-RPC)
- Health: built into the SDK
