#!/bin/bash
# ============================================================
# Convert WebM/other formats to MP3 for Yandex SpeechKit
# Usage: ./convert-audio.sh input.webm output.mp3
# ============================================================

set -euo pipefail

INPUT="${1:?Usage: convert-audio.sh <input_file> [output_file]}"
OUTPUT="${2:-${INPUT%.*}.mp3}"

# Validate input exists
if [ ! -f "$INPUT" ]; then
    echo "ERROR: Input file not found: $INPUT" >&2
    exit 1
fi

# Get file extension
EXT="${INPUT##*.}"
EXT_LOWER=$(echo "$EXT" | tr '[:upper:]' '[:lower:]')

# If already MP3, just copy
if [ "$EXT_LOWER" = "mp3" ]; then
    if [ "$INPUT" != "$OUTPUT" ]; then
        cp "$INPUT" "$OUTPUT"
    fi
    echo "OK: Already MP3 — $OUTPUT"
    exit 0
fi

# Convert with ffmpeg
# -c:a libmp3lame   — MP3 codec
# -b:a 128k         — 128kbps bitrate (good quality, reasonable size)
# -ar 48000         — 48kHz sample rate (SpeechKit optimal)
# -ac 1             — mono (sufficient for speech)
# -y                — overwrite output without asking
echo "Converting: $INPUT → $OUTPUT"
ffmpeg -i "$INPUT" \
    -c:a libmp3lame \
    -b:a 128k \
    -ar 48000 \
    -ac 1 \
    -y \
    "$OUTPUT" \
    2>/dev/null

if [ $? -eq 0 ]; then
    INPUT_SIZE=$(stat -c%s "$INPUT" 2>/dev/null || stat -f%z "$INPUT")
    OUTPUT_SIZE=$(stat -c%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT")
    echo "OK: $INPUT ($INPUT_SIZE bytes) → $OUTPUT ($OUTPUT_SIZE bytes)"
else
    echo "ERROR: Conversion failed for $INPUT" >&2
    exit 1
fi
