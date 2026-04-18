#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/3] Preprocess sample data"
python3 preprocess.py

echo "[2/3] Anomalies and forecasts are triggered via API from UI"
echo "Done."

