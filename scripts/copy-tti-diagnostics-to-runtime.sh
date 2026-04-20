#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$REPO/pages/reference/tti-diagnostics"
DEST_DIR="${1:-$REPO/runtime/pages}"

mkdir -p "$DEST_DIR"

for page in {701..710}; do
    src="$SRC_DIR/P${page}.tti"
    dest="$DEST_DIR/P${page}.tti"

    if [ ! -f "$src" ]; then
        echo "Missing source file: $src" >&2
        exit 1
    fi

    cp -f "$src" "$dest"
    echo "Copied P${page}.tti -> $dest"
done
