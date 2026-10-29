from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """配置结构：核心运行值来自项目根目录的 .env，可选项带安全默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    ollama_base_url: str
    ollama_default_model: str
    database_pool_size: int
    database_max_overflow: int
    database_pool_timeout: float
    database_pool_recycle: int
    ollama_global_concurrency: int
    ollama_model_concurrency: int
    ollama_queue_timeout: float
    ollama_models_cache_ttl: float

    # 管理接口（/backend/api-keys）访问口令。留空表示管理接口整体禁用。
    admin_token: str = ""
    # CORS 允许来源，逗号分隔；"*" 表示不限制（此时不会携带凭证）。
    cors_allow_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def allow_anonymous_cors(self) -> bool:
        """通配来源下必须关闭凭证，否则浏览器会拒绝跨域响应。"""
        return self.cors_allow_origins.strip() != "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def to_sync_database_url(url: str) -> str:
    """Alembic 使用同步驱动；应用运行时仍用 asyncpg。"""
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        .replace("postgres+asyncpg://", "postgresql+psycopg2://", 1)
    )
