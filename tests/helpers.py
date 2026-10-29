"""测试辅助：构造不依赖 .env 的 Settings 实例。"""
from app.config import Settings

REQUIRED = {
    "database_url": "postgresql+asyncpg://u:p@127.0.0.1:5432/db",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_default_model": "qwen2.5:7b",
    "database_pool_size": 5,
    "database_max_overflow": 5,
    "database_pool_timeout": 10,
    "database_pool_recycle": 1800,
    "ollama_global_concurrency": 2,
    "ollama_model_concurrency": 1,
    "ollama_queue_timeout": 5,
    "ollama_models_cache_ttl": 5,
}


def build_settings(**overrides) -> Settings:
    """初始化参数优先级高于环境变量与 .env。"""
    return Settings(**{**REQUIRED, **overrides})
