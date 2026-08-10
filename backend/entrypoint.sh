#!/usr/bin/env bash
set -euo pipefail

uv run alembic upgrade head
uv run python -m app.seed
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
