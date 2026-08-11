#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
"$project_root/stop.sh"
"$project_root/start.sh"
