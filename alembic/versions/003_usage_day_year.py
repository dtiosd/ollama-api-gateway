"""init daily and yearly usage

Revision ID: 003_usage_day_year
Revises: 002_key_status_week
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_usage_day_year"
down_revision: Union[str, None] = "002_key_status_week"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_usage_table(name: str, period_col: str, period_len: int, uq_name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=False),
        sa.Column(period_col, sa.String(length=period_len), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_key.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key_id", period_col, name=uq_name),
    )
    op.create_index(f"ix_{name}_api_key_id", name, ["api_key_id"])
    op.create_index(f"ix_{name}_{period_col}", name, [period_col])


def upgrade() -> None:
    _create_usage_table("api_usage_day", "year_day", 10, "uq_api_usage_key_day")
    _create_usage_table("api_usage_year", "year", 4, "uq_api_usage_key_year")


def downgrade() -> None:
    op.drop_index("ix_api_usage_year_year", table_name="api_usage_year")
    op.drop_index("ix_api_usage_year_api_key_id", table_name="api_usage_year")
    op.drop_table("api_usage_year")
    op.drop_index("ix_api_usage_day_year_day", table_name="api_usage_day")
    op.drop_index("ix_api_usage_day_api_key_id", table_name="api_usage_day")
    op.drop_table("api_usage_day")
