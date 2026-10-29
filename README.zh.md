[English](README.md) | **中文**

# ollama-api-gateway

基于 FastAPI + langchain-ollama 的 **OpenAI / Anthropic 兼容网关**：把本地 [Ollama](https://ollama.com) 服务包装成标准 API，并支持流式输出、多模态、思考模式、客户端工具调用、向量接口，同时用 PostgreSQL + Alembic 管理 API Key 与 token 用量。

适用场景：团队或个人自建的私有模型网关，需要「一把 Key 对应一个模型 + 额度可控 + 用量可查」。

## 功能

- `POST /v1/chat/completions`：OpenAI 兼容聊天（需 API Key），base URL 为 `/v1`
- `POST /v1/embeddings`：OpenAI 兼容向量接口，转发 Ollama `/api/embed`
- `GET /v1/models`：转发 Ollama 已安装模型列表（密钥绑定模型时只返回该模型）
- `POST /anthropic/v1/messages`：Anthropic Messages 兼容（Claude Code / CC Switch），base URL 为 `/anthropic`
- `POST /anthropic/v1/messages/count_tokens`：按请求体粗略估算 input tokens
- `GET /`：管理页，生成 / 列表 / 改额度 / 禁用删除 API Key，按日、周、月、年查看用量
- `GET /health`：健康检查
- 鉴权：`Authorization: Bearer sk-xxx` 或 `X-API-Key: sk-xxx`
- 配额：按 token 累计扣减，用尽返回 `402`；配额与模型绑定对所有密钥一律生效，无豁免名单
- 并发：全局与单模型两级信号量，超载排队超时返回 `429`

## 快速开始

### 1. 环境要求

- Python 3.11+
- PostgreSQL 12+
- 可访问的 Ollama 服务（`ollama serve`）

### 2. 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

编辑 `.env`，至少填写 `DATABASE_URL`、`OLLAMA_BASE_URL`、`OLLAMA_DEFAULT_MODEL`，并**务必设置 `ADMIN_TOKEN`**（管理接口的访问口令，留空则管理接口不可用）：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. 初始化数据库

先在 PostgreSQL 中创建数据库（库名与 `.env` 里 `DATABASE_URL` 一致），然后：

```bash
alembic upgrade head
```

应用运行时使用 `postgresql+asyncpg://`；Alembic 迁移会自动换成同步的 `postgresql+psycopg2://`（Windows 上可避开 asyncpg 的 WinError 64）。

### 4. 启动

```bash
# 开发
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# 生产（不要使用 --reload）
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开 <http://127.0.0.1:8001/> ，在「管理口令」框输入 `ADMIN_TOKEN` 的值并保存，即可生成 API Key。

### 5. 调用示例

OpenAI 兼容接口：

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-你的密钥" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

- 流式输出把 `stream` 设为 `true`（SSE）。
- 思考模式可传 `"think": true`，或 OpenAI SDK 的 `extra_body={"reasoning": true}`。
- 工具调用按 OpenAI 格式传入 `tools`；网关只返回 `tool_calls`，不在服务端执行工具。
- 向量接口：`POST /v1/embeddings`，body 为 `{"model":"nomic-embed-text","input":["文本"]}`，见 [examples/embeddings.py](examples/embeddings.py)。

Anthropic / Claude Code 使用独立前缀，不和 `/v1` 混用：

```bash
curl -N http://127.0.0.1:8001/anthropic/v1/messages \
  -H "x-api-key: sk-你的密钥" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:7b","max_tokens":256,"stream":true,"messages":[{"role":"user","content":"你好"}]}'
```

响应为 Anthropic SSE（`message_start`、`content_block_delta`、`message_stop`）；`curl -N` 用于关闭 curl 自身缓冲。

CC Switch 配置：接口格式选 **Anthropic Messages**，请求地址填 `http://<主机>:<端口>/anthropic`（客户端会自行请求 `/v1/messages`），API Key 用管理页生成的 `sk-...`，Sonnet / Opus / Haiku 映射成 Ollama 里真实存在的模型名。

更多可运行脚本见 [examples/](examples/)（示例模型名请替换成你本机 `ollama list` 的结果）。

## 配置项

所有运行配置来自项目根目录的 `.env`（`.env` 已被 `.gitignore` 忽略，不要提交）。

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串，形如 `postgresql+asyncpg://user:pass@127.0.0.1:5432/dbname` |
| `OLLAMA_BASE_URL` | Ollama 服务地址 |
| `OLLAMA_DEFAULT_MODEL` | 请求未指定 `model` 且密钥未绑定模型时使用 |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` / `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_RECYCLE` | 每个 Uvicorn worker 的连接池 |
| `OLLAMA_GLOBAL_CONCURRENCY` / `OLLAMA_MODEL_CONCURRENCY` / `OLLAMA_QUEUE_TIMEOUT` / `OLLAMA_MODELS_CACHE_TTL` | Ollama 并发与排队控制 |
| `ADMIN_TOKEN` | 管理接口 `/backend/api-keys` 的访问口令；**留空则管理接口整体禁用** |
| `CORS_ALLOW_ORIGINS` | 允许来源，逗号分隔；`*` 表示不限制（此时不携带凭证） |

### 并发建议

并发限制按 Uvicorn 进程计算。启动多个 worker 时，总模型并发约为 `worker 数量 × OLLAMA_MODEL_CONCURRENCY`。单 GPU 建议先用一个 worker，再根据显存与压测结果调整每模型并发。

## 安全说明

请阅读 [SECURITY.md](SECURITY.md)。要点：

- 管理接口需要在请求头 `X-Admin-Token` 中携带 `ADMIN_TOKEN`，使用 `hmac.compare_digest` 比对；未配置口令时接口直接返回 `503`。
- 管理页保存的密钥为明文（便于分发），数据库泄露等于密钥泄露；请限制数据库访问并做好备份加密。
- 配额扣减与绑定模型校验对**所有密钥一律生效**，代码里没有任何按用户名豁免的分支；需要大额度请在管理页把 `token_quota` 调高（字段为 BIGINT），走的仍是正常、可审计的路径。
- 公网部署务必放在反向代理之后（[deploy/nginx-ollama-api.conf](deploy/nginx-ollama-api.conf) 提供了流式缓冲关闭与 `/backend/` 段内网限流的样例），并配合 TLS。

## 项目结构

```
app/
  main.py              # FastAPI 入口
  config.py            # 配置（.env）
  api/                 # 路由：鉴权、聊天、Anthropic、密钥管理
  llm/                 # Ollama 客户端、并发、Anthropic 协议转换
  db/                  # SQLAlchemy 模型与仓储
  schemas/             # Pydantic schema
alembic/               # 数据库迁移
templates/ static/     # 管理页
examples/              # 客户端调用示例
tests/                 # 单元测试
deploy/                # 反向代理样例配置
```

## 开发

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

改动数据模型后生成并执行迁移：

```bash
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

### CI 跑什么

`.gitlab-ci.yml` 共三个 job：`ruff`、`pytest`，以及 `migration-drift` —— 后者在一个全新的
PostgreSQL 服务上重放全部迁移，再跑 `alembic check`。漂移检查失败说明 `app/db/models.py`
与迁移历史不一致，因此提交模型改动前先在本地跑一次。

列注释被有意排除在比对之外：历史迁移里的注释文字已和 `models.py` 漂移，而注释属于文档、
不是结构。表、列、类型、可空性、索引、约束仍然全量比对（见 `alembic/env.py` 的
`AUTOGEN_PLUGINS`）。

### 编码与行尾

`.editorconfig` 与 `.gitattributes` 把整个仓库固定为 UTF-8 + LF，因此入库内容不依赖任何人的
`core.autocrlf` 配置。有一个例外必须记住：`alembic.ini` 要保持**纯 ASCII** —— Alembic 用操作系统
区域编码读取它（中文 Windows 下是 GBK），一句非 ASCII 注释就会让所有 `alembic` 命令报
`UnicodeDecodeError`。

贡献流程与提交要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 术语与归属

Ollama 是 Ollama Inc. 的商标，项目名称与图标素材归其所有；本项目为独立的兼容网关，未获得 Ollama 官方背书或 affiliation。仓库内 `static/ollama.png` 仅用于标识所兼容的后端服务。

## 许可

[MIT](LICENSE)
