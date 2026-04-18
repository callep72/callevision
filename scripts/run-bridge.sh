#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${1:-$REPO/config/callevision.yaml}"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found: $CONFIG" >&2
    echo "Copy config/callevision.yaml.example to config/callevision.yaml and edit it." >&2
    exit 1
fi

cd "$REPO"
PYTHONPATH="$REPO/src" exec python -m callevision.bridge "$CONFIG"
