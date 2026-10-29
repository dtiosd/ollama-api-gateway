**English** | [中文](README.zh.md)

# ollama-api-gateway

An **OpenAI / Anthropic compatible gateway** built with FastAPI + langchain-ollama. It wraps a local [Ollama](https://ollama.com) server behind standard APIs, supporting streaming, multimodal input, thinking mode, client-side tool calling and embeddings, while managing API keys and token usage in PostgreSQL (Alembic for migrations).

Good fit for: a self-hosted team or personal model gateway that needs "one key per model, enforced quota, visible usage".

## Features

- `POST /v1/chat/completions` — OpenAI-compatible chat (requires an API key), base URL is `/v1`
- `POST /v1/embeddings` — OpenAI-compatible embeddings, forwarded to Ollama `/api/embed`
- `GET /v1/models` — installed Ollama models (a key bound to a model only sees that model)
- `POST /anthropic/v1/messages` — Anthropic Messages compatible (Claude Code / CC Switch), base URL is `/anthropic`
- `POST /anthropic/v1/messages/count_tokens` — rough input-token estimate from the request body
- `GET /` — admin UI: create / list / top up / disable / delete API keys, usage by day, week, month and year
- `GET /health` — health check
- Auth: `Authorization: Bearer sk-xxx` or `X-API-Key: sk-xxx`
- Quota: cumulative token deduction; returns `402` when exhausted. Quota and model binding apply to every key — there is no exemption list
- Concurrency: global + per-model semaphores; queue timeout returns `429`

## Quick start

### 1. Requirements

- Python 3.11+
- PostgreSQL 12+
- A reachable Ollama server (`ollama serve`)

### 2. Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least `DATABASE_URL`, `OLLAMA_BASE_URL` and `OLLAMA_DEFAULT_MODEL`. **Always set `ADMIN_TOKEN`** — it is the passphrase for the management API (leave it empty and the management API stays disabled):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Initialize the database

Create the database in PostgreSQL first (the name must match `DATABASE_URL` in `.env`), then:

```bash
alembic upgrade head
```

The app runs on `postgresql+asyncpg://`; Alembic switches to the synchronous `postgresql+psycopg2://` driver automatically (this avoids asyncpg's WinError 64 on Windows).

### 4. Run

```bash
# development
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# production (do not use --reload)
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001/> , paste your `ADMIN_TOKEN` into the passphrase field to unlock the UI, then create an API key.

### 5. Call the API

OpenAI-compatible:

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

- Set `stream` to `true` for SSE streaming.
- Thinking mode: pass `"think": true`, or `extra_body={"reasoning": true}` with the OpenAI SDK.
- Tool calling: send `tools` in the OpenAI format. The gateway only returns `tool_calls`; it never executes tools server-side.
- Embeddings: `POST /v1/embeddings` with `{"model":"nomic-embed-text","input":["some text"]}`, see [examples/embeddings.py](examples/embeddings.py).

Anthropic / Claude Code uses its own prefix and does not share `/v1`:

```bash
curl -N http://127.0.0.1:8001/anthropic/v1/messages \
  -H "x-api-key: sk-your-key" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:7b","max_tokens":256,"stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

Responses are Anthropic SSE (`message_start`, `content_block_delta`, `message_stop`); `curl -N` disables curl's own buffering so tokens print as they are generated.

For CC Switch: choose **Anthropic Messages** as the format, set the request URL to `http://<host>:<port>/anthropic` (the client appends `/v1/messages` itself), use the `sk-...` key from the admin UI, and map Sonnet / Opus / Haiku to model names that actually exist in your Ollama installation.

More runnable scripts live in [examples/](examples/) — replace the sample model names with the output of `ollama list`.

## Configuration

All runtime values come from `.env` in the project root (`.env` is git-ignored — never commit it).

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | PostgreSQL DSN, e.g. `postgresql+asyncpg://user:pass@127.0.0.1:5432/dbname` |
| `OLLAMA_BASE_URL` | Ollama server URL |
| `OLLAMA_DEFAULT_MODEL` | Used when the request omits `model` and the key has no bound model |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` / `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_RECYCLE` | Connection pool, per Uvicorn worker |
| `OLLAMA_GLOBAL_CONCURRENCY` / `OLLAMA_MODEL_CONCURRENCY` / `OLLAMA_QUEUE_TIMEOUT` / `OLLAMA_MODELS_CACHE_TTL` | Ollama concurrency and queue limits |
| `ADMIN_TOKEN` | Passphrase for `/backend/api-keys`; **if empty the whole management API is disabled** |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins; `*` means unrestricted (credentials are then disabled) |

### Concurrency notes

Limits are applied per Uvicorn process. With several workers, total per-model concurrency is roughly `workers × OLLAMA_MODEL_CONCURRENCY`. On a single GPU, start with one worker and tune `OLLAMA_MODEL_CONCURRENCY` from load-test results and available VRAM.

## Security

Read [SECURITY.md](SECURITY.md). The essentials:

- Model endpoints require a valid key: `401` for unknown/disabled keys, `402` for exhausted quota.
- The management API requires the `X-Admin-Token` header, compared against `ADMIN_TOKEN` with `hmac.compare_digest`; a mismatch returns `403`.
- With `ADMIN_TOKEN` unset the management routes return `503` — default closed, not default open.
- Quota deduction and the bound-model check are enforced for every key. There is no username-based exemption anywhere in the code; for effectively unlimited access, create a key with a very large `token_quota` (the column is BIGINT) so the request still goes through the normal, auditable path.
- API keys are stored in plaintext so they can be handed out from the UI. Lock down database access and encrypt backups.
- Ollama itself has no authentication: never expose `OLLAMA_BASE_URL` directly to the public network.
- Put the gateway behind a reverse proxy with TLS for anything public — [deploy/nginx-ollama-api.conf](deploy/nginx-ollama-api.conf) shows streaming settings and an example of restricting `/backend/` to trusted networks.

## Project layout

```
app/
  main.py              # FastAPI entry point
  config.py            # settings loaded from .env
  api/                 # routes: auth, chat/embeddings, anthropic, key management
  llm/                 # Ollama client, concurrency, Anthropic protocol mapping
  db/                  # SQLAlchemy models and repositories
  schemas/             # Pydantic schemas
alembic/               # database migrations
templates/ static/     # admin UI
examples/              # client-side example scripts
tests/                 # unit tests
deploy/                # reverse-proxy samples
```

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

The unit tests do not need PostgreSQL or Ollama (`tests/conftest.py` supplies test environment variables).

After changing the data model, generate and apply a migration:

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### What CI runs

`.gitlab-ci.yml` has three jobs: `ruff`, `pytest`, and `migration-drift`, which replays every
migration against a fresh PostgreSQL service and then runs `alembic check`. A failing drift check
means `app/db/models.py` and the migration history disagree, so run it locally before committing
model changes.

Column comments are deliberately excluded from that comparison: the wording in the historical
migrations drifted from `models.py`, and comments are documentation rather than schema. Tables,
columns, types, nullability, indexes and constraints are still compared in full (see
`AUTOGEN_PLUGINS` in `alembic/env.py`).

### Encoding and line endings

`.editorconfig` and `.gitattributes` pin UTF-8 + LF for the whole repository, so the stored
content does not depend on anyone's `core.autocrlf` setting. One exception worth remembering:
`alembic.ini` must stay **pure ASCII**, because Alembic reads it with the OS locale encoding
(GBK on Chinese Windows) and a non-ASCII comment there makes every `alembic` command fail with
`UnicodeDecodeError`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and commit conventions.

## Trademarks

Ollama is a trademark of Ollama Inc. This is an independent compatibility gateway, not affiliated with or endorsed by Ollama. `static/ollama.png` is used only to identify the backend service this project talks to.

## License

[MIT](LICENSE)
