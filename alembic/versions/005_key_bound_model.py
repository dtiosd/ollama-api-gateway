"""bind api_key to a model

Revision ID: 005_key_bound_model
Revises: 004_usage_model
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_key_bound_model"
down_revision: Union[str, None] = "004_usage_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_key",
        sa.Column(
            "bound_model",
            sa.String(length=128),
            nullable=False,
            server_default="",
            comment="绑定的模型名，该密钥只能调用此模型",
        ),
    )
    op.drop_index("ix_api_key_username", table_name="api_key")
    op.create_index("ix_api_key_username", "api_key", ["username"], unique=False)
    op.create_index("ix_api_key_bound_model", "api_key", ["bound_model"])
    op.create_unique_constraint(
        "uq_api_key_username_model", "api_key", ["username", "bound_model"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_api_key_username_model", "api_key", type_="unique")
    op.drop_index("ix_api_key_bound_model", table_name="api_key")
    op.drop_index("ix_api_key_username", table_name="api_key")
    op.create_index("ix_api_key_username", "api_key", ["username"], unique=True)
    op.drop_column("api_key", "bound_model")
