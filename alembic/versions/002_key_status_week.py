"""init api_key disable, unique username, weekly usage

Revision ID: 002_key_status_week
Revises: 001_init
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_key_status_week"
down_revision: Union[str, None] = "001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_key",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否启用；禁用后不可调用模型接口",
        ),
    )
    op.drop_index("ix_api_key_username", table_name="api_key")
    op.create_index("ix_api_key_username", "api_key", ["username"], unique=True)

    op.create_table(
        "api_usage_week",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=False, comment="API 密钥 ID"),
        sa.Column(
            "year_week",
            sa.String(length=8),
            nullable=False,
            comment="ISO 周，格式 YYYY-Www",
        ),
        sa.Column(
            "prompt_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="输入 token 数",
        ),
        sa.Column(
            "completion_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="输出 token 数",
        ),
        sa.Column(
            "total_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="总 token 数",
        ),
        sa.Column(
            "request_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="请求次数",
        ),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_key.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key_id", "year_week", name="uq_api_usage_key_week"),
    )
    op.create_index("ix_api_usage_week_api_key_id", "api_usage_week", ["api_key_id"])
    op.create_index("ix_api_usage_week_year_week", "api_usage_week", ["year_week"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_week_year_week", table_name="api_usage_week")
    op.drop_index("ix_api_usage_week_api_key_id", table_name="api_usage_week")
    op.drop_table("api_usage_week")
    op.drop_index("ix_api_key_username", table_name="api_key")
    op.create_index("ix_api_key_username", "api_key", ["username"], unique=False)
    op.drop_column("api_key", "is_active")
