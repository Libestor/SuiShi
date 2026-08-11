"""basket principals in snapshots

Revision ID: 7b2d9f01c4a8
Revises: c41b6df04e92
Create Date: 2026-08-11 18:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b2d9f01c4a8"
down_revision: Union[str, None] = "c41b6df04e92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_snapshots",
        sa.Column("basket_principals", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_snapshots", "basket_principals")
