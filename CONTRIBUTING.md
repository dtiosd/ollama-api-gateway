# 贡献指南

感谢参与。开始前请先阅读 [README.md](README.md) 的「开发」一节。

## 环境准备

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements-dev.txt
copy .env.example .env        # 按需填写 DATABASE_URL / OLLAMA_BASE_URL 等
alembic upgrade head          # 需要可连接的 PostgreSQL
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## 提交前自检

```bash
ruff check .
python -m pytest
```

单元测试不依赖 PostgreSQL 与 Ollama（见 `tests/conftest.py` 提供的测试环境变量）。需要真实外部服务的验证请在本地手动跑并在 PR 描述里写明结论。

## 改动约定

- **分层**：路由只做协议转换与错误码映射（`app/api/`），模型调用与并发在 `app/llm/`，SQL 与事务在 `app/db/repository.py`。
- **配置**：新增配置项一律走 `app/config.py` + `.env` / `.env.example`，不要在代码里写死地址、密钥、模型名。
- **数据库**：改动 `app/db/models.py` 后必须生成 Alembic 迁移
  `alembic revision --autogenerate -m "描述"`，并确认迁移在空库上 `alembic upgrade head` 可跑通。
- **兼容性**：`/v1/chat/completions`、`/v1/embeddings`、`/anthropic/v1/messages` 的响应结构遵循 OpenAI / Anthropic 公开规范，字段改动需要说明对客户端 SDK 的影响。
- **错误码**：鉴权失败 `401`、配额用尽 `402`、密钥被禁用 `401`、管理口令错误 `403`、模型未配置 `400`、上游失败 `502`、排队超时 `429`。

## 提交与 Pull Request

- 分支名：`feat/xxx`、`fix/xxx`、`refactor/xxx`、`docs/xxx`。
- 提交信息使用现在时祈使句，例如 `fix: 流式中断时不再跳过用量记账`。
- 一个 PR 只解决一件事；行为变更请附带 `curl` 或示例脚本的前后对比。
- 请不要提交 `.env`、数据库导出、真实 API Key、内部主机地址或员工账号；`ADMIN_TOKEN`、密钥一律用占位值。

## Issue

Bug 报告请包含：版本或 commit、复现步骤、请求体（脱敏）、期望与实际响应、网关与 Ollama 的日志片段。
