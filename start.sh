#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
compose_file="$project_root/compose.production.yaml"

if [[ ! -f "$project_root/.env" ]]; then
  echo "Missing $project_root/.env. Copy .env.production.example and set unique secrets." >&2
  exit 1
fi

cd "$project_root"
docker compose --env-file .env -f "$compose_file" config --quiet
docker compose --env-file .env -f "$compose_file" up --detach --build --remove-orphans
docker compose --env-file .env -f "$compose_file" ps
