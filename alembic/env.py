from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings, to_sync_database_url
from app.db import Base
from app.db import models  # noqa: F401 — register models

# Windows 中文环境：服务端报错若为 GBK，避免再被当成 UTF-8 解不出来
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 列/表注释只是文档信息，历史迁移里的注释文字已和 models.py 漂移。继续比对注释
# 会让 `alembic check` 在没有任何真实结构差异的情况下报错，因此这里加载全部内置
# 比对插件、但排除注释比对：表、列、类型、可空性、索引、约束仍然全量比对。
# 依赖 Alembic 1.18+ 的 autogenerate 插件机制（`*` 通配 + `~` 排除）。
AUTOGEN_PLUGINS = ["alembic.autogenerate.*", "~alembic.autogenerate.comments"]

sync_url = to_sync_database_url(get_settings().database_url)
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        autogenerate_plugins=AUTOGEN_PLUGINS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
        connect_args={"client_encoding": "utf8"},
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                autogenerate_plugins=AUTOGEN_PLUGINS,
            )
            with context.begin_transaction():
                context.run_migrations()
    except UnicodeDecodeError as e:
        raise RuntimeError(
            "无法连接 PostgreSQL（常见原因：.env 未配置、密码错误、或库不存在）。"
            "请确认已复制 .env.example 为 .env，且 DATABASE_URL 与本机账号一致。"
        ) from e
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
