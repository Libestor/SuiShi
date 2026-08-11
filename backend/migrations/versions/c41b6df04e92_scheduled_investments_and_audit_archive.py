"""scheduled investments and audit archive

Revision ID: c41b6df04e92
Revises: 8b72c4d91f30
Create Date: 2026-08-11 09:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c41b6df04e92"
down_revision: Union[str, None] = "8b72c4d91f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_investments",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("data_source_id", sa.String(length=36), nullable=False),
        sa.Column("amount_cny", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("time_of_day", sa.String(length=5), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=48), nullable=False),
        sa.Column("retry_attempts", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_investments_asset_id"), "scheduled_investments", ["asset_id"])
    op.create_index(op.f("ix_scheduled_investments_data_source_id"), "scheduled_investments", ["data_source_id"])
    op.create_index(op.f("ix_scheduled_investments_next_run_at"), "scheduled_investments", ["next_run_at"])
    op.create_table(
        "scheduled_investment_runs",
        sa.Column("scheduled_investment_id", sa.String(length=36), nullable=False),
        sa.Column("ledger_entry_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_source_run_ids", sa.JSON(), nullable=False),
        sa.Column("quote_payload", sa.JSON(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=20, scale=10), nullable=True),
        sa.Column("units_delta", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("amount_cny", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ledger_entry_id"], ["ledger_entries.id"]),
        sa.ForeignKeyConstraint(["scheduled_investment_id"], ["scheduled_investments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_investment_runs_ledger_entry_id"), "scheduled_investment_runs", ["ledger_entry_id"])
    op.create_index(op.f("ix_scheduled_investment_runs_scheduled_for"), "scheduled_investment_runs", ["scheduled_for"])
    op.create_index(op.f("ix_scheduled_investment_runs_scheduled_investment_id"), "scheduled_investment_runs", ["scheduled_investment_id"])
    op.create_table(
        "archived_audit_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_archived_audit_records_occurred_at"), "archived_audit_records", ["occurred_at"])
    op.create_index(op.f("ix_archived_audit_records_source_id"), "archived_audit_records", ["source_id"])
    op.create_index(op.f("ix_archived_audit_records_source_type"), "archived_audit_records", ["source_type"])


def downgrade() -> None:
    op.drop_table("archived_audit_records")
    op.drop_table("scheduled_investment_runs")
    op.drop_table("scheduled_investments")
