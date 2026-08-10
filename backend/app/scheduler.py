from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import DataSource
from app.services.datasources import execute_data_source
from app.services.portfolio import save_portfolio_snapshot
from app.services.notifications import evaluate_rules


logger = logging.getLogger(__name__)


def snapshot_job() -> None:
    with SessionLocal() as db:
        try:
            snapshot = save_portfolio_snapshot(db, source="scheduler")
            evaluate_rules(db, {"portfolio": {"total_asset_cny": snapshot.total_asset_cny}})
        except Exception:
            logger.exception("Failed to save scheduled portfolio snapshot")


def data_source_job() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        sources = list(
            db.scalars(
                select(DataSource).where(
                    DataSource.deleted_at.is_(None),
                    DataSource.enabled.is_(True),
                    or_(DataSource.next_run_at.is_(None), DataSource.next_run_at <= now),
                )
            )
        )
        for source in sources:
            try:
                execute_data_source(db, source)
            except Exception:
                logger.exception("Failed to run data source %s", source.id)


def create_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        return None
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        snapshot_job,
        "interval",
        minutes=settings.snapshot_interval_minutes,
        id="portfolio-snapshot",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        data_source_job,
        "interval",
        minutes=1,
        id="data-source-dispatch",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
