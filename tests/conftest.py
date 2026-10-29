"""测试用环境变量：在无 .env 的 CI 环境下也能导入应用配置。

真实环境变量优先级高于 .env，因此这里给出的值会覆盖开发者本地配置。
"""
import os

TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:5432/ollama_api_test",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "OLLAMA_DEFAULT_MODEL": "qwen2.5:7b",
    "DATABASE_POOL_SIZE": "5",
    "DATABASE_MAX_OVERFLOW": "5",
    "DATABASE_POOL_TIMEOUT": "10",
    "DATABASE_POOL_RECYCLE": "1800",
    "OLLAMA_GLOBAL_CONCURRENCY": "2",
    "OLLAMA_MODEL_CONCURRENCY": "1",
    "OLLAMA_QUEUE_TIMEOUT": "5",
    "OLLAMA_MODELS_CACHE_TTL": "5",
    "ADMIN_TOKEN": "",
    "CORS_ALLOW_ORIGINS": "*",
}

for _key, _value in TEST_ENV.items():
    os.environ.setdefault(_key, _value)
