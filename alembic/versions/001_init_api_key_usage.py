"""init api_key and api_usage

Revision ID: 001_init
Revises:
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_key",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False, comment="用户名"),
        sa.Column(
            "api_key",
            sa.String(length=80),
            nullable=False,
            comment="API 密钥，格式 sk-xxx",
        ),
        sa.Column(
            "token_quota",
            sa.BigInteger(),
            nullable=False,
            server_default="100000",
            comment="剩余可用 token 数量",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="生成时间",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_key_api_key"), "api_key", ["api_key"], unique=True)
    op.create_index(op.f("ix_api_key_username"), "api_key", ["username"], unique=False)

    op.create_table(
        "api_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=False, comment="API 密钥 ID"),
        sa.Column(
            "year_month",
            sa.String(length=7),
            nullable=False,
            comment="年月，格式 YYYY-MM",
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
        sa.UniqueConstraint("api_key_id", "year_month", name="uq_api_usage_key_month"),
    )
    op.create_index(
        op.f("ix_api_usage_api_key_id"), "api_usage", ["api_key_id"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_year_month"), "api_usage", ["year_month"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_api_usage_year_month"), table_name="api_usage")
    op.drop_index(op.f("ix_api_usage_api_key_id"), table_name="api_usage")
    op.drop_table("api_usage")
    op.drop_index(op.f("ix_api_key_username"), table_name="api_key")
    op.drop_index(op.f("ix_api_key_api_key"), table_name="api_key")
    op.drop_table("api_key")
