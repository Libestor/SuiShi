#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
cd "$project_root"

# Deliberately keeps the SQLite database and uploaded data bind mounts intact.
docker compose --env-file .env -f "$project_root/compose.production.yaml" down
