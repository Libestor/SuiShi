#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
backup_dir="$project_root/backups"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_file="$backup_dir/investment-overview-$timestamp.sql"

mkdir -p "$backup_dir"

docker compose -f "$project_root/compose.yaml" exec -T mysql \
  sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  > "$backup_file"

if [[ ! -s "$backup_file" ]]; then
  echo "Backup failed: $backup_file is empty" >&2
  exit 1
fi

echo "$backup_file"
