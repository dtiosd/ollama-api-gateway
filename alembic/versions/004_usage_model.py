"""add model_name to usage tables

Revision ID: 004_usage_model
Revises: 003_usage_day_year
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_usage_model"
down_revision: Union[str, None] = "003_usage_day_year"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    ("api_usage", "year_month", "uq_api_usage_key_month", "uq_api_usage_key_month_model"),
    ("api_usage_week", "year_week", "uq_api_usage_key_week", "uq_api_usage_key_week_model"),
    ("api_usage_day", "year_day", "uq_api_usage_key_day", "uq_api_usage_key_day_model"),
    ("api_usage_year", "year", "uq_api_usage_key_year", "uq_api_usage_key_year_model"),
)


def upgrade() -> None:
    for table, period_col, old_uq, new_uq in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "model_name",
                sa.String(length=128),
                nullable=False,
                server_default="",
                comment="调用的模型名",
            ),
        )
        op.drop_constraint(old_uq, table, type_="unique")
        op.create_unique_constraint(new_uq, table, ["api_key_id", period_col, "model_name"])
        op.create_index(f"ix_{table}_model_name", table, ["model_name"])


def downgrade() -> None:
    for table, period_col, old_uq, new_uq in reversed(_TABLES):
        op.drop_index(f"ix_{table}_model_name", table_name=table)
        op.drop_constraint(new_uq, table, type_="unique")
        op.create_unique_constraint(old_uq, table, ["api_key_id", period_col])
        op.drop_column(table, "model_name")
