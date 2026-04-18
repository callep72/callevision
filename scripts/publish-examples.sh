#!/usr/bin/env bash
# Publish all example TTI pages to MQTT with the retain flag.
# Reads each pages/examples/P{N}.tti and publishes to callevision/pages/{N}/raw.
#
# Usage:
#   MQTT_HOST=192.168.1.50 MQTT_USER=callevision MQTT_PASS=changeme \
#     scripts/publish-examples.sh
#
# Or pass broker args directly:
#   scripts/publish-examples.sh -h 192.168.1.50 -u callevision -P changeme

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLES_DIR="$REPO/pages/examples"

# Collect any extra args passed on the command line (e.g. -h host -u user -P pass)
MQTT_ARGS=()

if [[ "${MQTT_HOST:-}" ]]; then
    MQTT_ARGS+=(-h "$MQTT_HOST")
fi
if [[ "${MQTT_USER:-}" ]]; then
    MQTT_ARGS+=(-u "$MQTT_USER")
fi
if [[ "${MQTT_PASS:-}" ]]; then
    MQTT_ARGS+=(-P "$MQTT_PASS")
fi
if [[ "${MQTT_PORT:-}" ]]; then
    MQTT_ARGS+=(-p "$MQTT_PORT")
fi

# Append any positional/flag args the caller supplied
MQTT_ARGS+=("$@")

shopt -s nullglob
files=("$EXAMPLES_DIR"/P*.tti)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No example files found in $EXAMPLES_DIR" >&2
    exit 1
fi

for tti in "${files[@]}"; do
    filename="$(basename "$tti")"
    # Extract page number from P{N}.tti
    page="${filename#P}"
    page="${page%.tti}"

    topic="callevision/pages/$page/raw"
    echo "Publishing $filename → $topic"
    mosquitto_pub "${MQTT_ARGS[@]}" -t "$topic" -r -f "$tti"
done

echo "Done — ${#files[@]} page(s) published."
