#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 scripts/update_tennis_data.py
python3 scripts/check_data_freshness.py tennis
