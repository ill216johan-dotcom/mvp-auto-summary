#!/bin/bash
# ============================================================
# Simulate a Jibri recording for testing n8n workflows
# Creates a test audio file in /mnt/recordings/YYYY/MM/DD/
#
# Usage:
#   ./simulate-recording.sh              # Uses LEAD_ID=99999
#   ./simulate-recording.sh 12345        # Uses LEAD_ID=12345
#   ./simulate-recording.sh 12345 /path/to/real.mp3  # Uses real audio
# ============================================================

set -euo pipefail

LEAD_ID="${1:-99999}"
REAL_FILE="${2:-}"
DATE=$(date +%Y/%m/%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M)
FILENAME="${LEAD_ID}_${TIMESTAMP}.mp3"
TARGET_DIR="/mnt/recordings/${DATE}"
TARGET_PATH="${TARGET_DIR}/${FILENAME}"

echo "============================================"
echo "  Simulating Jibri recording"
echo "============================================"
echo "  LEAD_ID:  $LEAD_ID"
echo "  Filename: $FILENAME"
echo "  Target:   $TARGET_PATH"
echo ""

# Create date directory
mkdir -p "$TARGET_DIR"

if [ -n "$REAL_FILE" ]; then
    # Use real audio file
    if [ ! -f "$REAL_FILE" ]; then
        echo "ERROR: Source file not found: $REAL_FILE" >&2
        exit 1
    fi
    cp "$REAL_FILE" "$TARGET_PATH"
    echo "OK: Copied real audio file"
else
    # Generate 10-second silent MP3 for testing
    if command -v ffmpeg &>/dev/null; then
        ffmpeg -f lavfi -i anullsrc=r=48000:cl=mono -t 10 \
            -c:a libmp3lame -b:a 128k \
            -y "$TARGET_PATH" 2>/dev/null
        echo "OK: Generated 10s silent MP3 (test file)"
    else
        # Fallback: create a tiny valid MP3 header
        echo "WARNING: ffmpeg not found. Creating minimal test file."
        # Minimal MP3 frame (not really valid audio, but detectable by n8n)
        printf '\xff\xfb\x90\x00' > "$TARGET_PATH"
        echo "OK: Created minimal test file (not real audio)"
    fi
fi

echo ""
echo "File created: $TARGET_PATH"
echo "Size: $(stat -c%s "$TARGET_PATH" 2>/dev/null || stat -f%z "$TARGET_PATH") bytes"
echo ""
echo "n8n should pick this up on next scan cycle (every 5 min)."
echo "Check n8n executions at http://localhost:5678/executions"
