"""platform settings and source asset bindings

Revision ID: 5dc9e4a123b7
Revises: 01f61bd5e042
Create Date: 2026-08-10 08:47:06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5dc9e4a123b7"
down_revision: Union[str, None] = "01f61bd5e042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(sa.Column("asset_ids", sa.JSON(), nullable=True))
    op.execute("UPDATE data_sources SET asset_ids = '[]' WHERE asset_ids IS NULL")
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.alter_column("asset_ids", existing_type=sa.JSON(), nullable=False)

    op.create_table(
        "platform_settings",
        sa.Column("allocation_mode", sa.String(length=20), nullable=False),
        sa.Column("growth_ratio", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("risk_ratio", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("default_contribution_cny", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_column("asset_ids")
