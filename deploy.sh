#!/bin/sh
# Copy the integration into a Home Assistant configuration directory (no symlink).
#   ./deploy.sh /path/to/config          e.g. ./deploy.sh /homeassistant
# Afterwards: check the configuration and restart Home Assistant Core.
set -e
CONFIG_DIR="${1:?usage: deploy.sh <home assistant config dir>}"
SRC="$(cd "$(dirname "$0")" && pwd)/custom_components/werktage"
DST="$CONFIG_DIR/custom_components/werktage"
python3 "$(dirname "$0")/tools/sync_vendor.py" --check
rm -rf "$DST" && mkdir -p "$DST"
cp -r "$SRC"/. "$DST"/
find "$DST" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "deployed to $DST ($(find "$DST" -type f | wc -l) files)"
