#!/bin/bash
set -e

PAGES_DIR="/home/calle/projects/callevision/pages"
VBIT2_DIR="/home/calle/projects/vbit2"
TELETEXT_BIN="/home/calle/projects/raspi-teletext/teletext"

# Ensure teletext mode is on
sudo /home/calle/projects/raspi-teletext/tvctl on

# Run the pipeline
cd "$VBIT2_DIR"
exec ./vbit2 --dir "$PAGES_DIR" | "$TELETEXT_BIN" -
