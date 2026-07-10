#!/bin/bash
# crv benchmark v1 — fixed-rate extraction vs crv scene-aware extraction
#
# For each test video, runs four methods:
#   A  fixed 1 fps      : ffmpeg -vf fps=1
#   B  fixed 0.5 fps    : ffmpeg -vf fps=0.5
#   C  crv default      : crv <video> --no-transcribe
#   D  crv --adaptive   : crv <video> --no-transcribe --adaptive
#
# Transcription is disabled everywhere (--no-transcribe): this benchmark
# measures frame extraction only, so Whisper time does not pollute timings.
#
# Outputs per video: results/<slug>/stats.csv (frames, seconds, crv log tail).
# Frames land in a work dir (default: ./work) — inspect, pick representative
# frames, then delete; they are not meant to be committed.
#
# Usage:
#   ./run_benchmark.sh                 # uses VIDEOS list below
#   WORK=/tmp/crv-bench ./run_benchmark.sh
#
# Requirements: ffmpeg, crv on PATH, perl (for sub-second timing on macOS).

set -u
BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$BENCH_DIR/work}"
RESULTS="$BENCH_DIR/results"
mkdir -p "$WORK" "$RESULTS"

# jfk-rice.mp4 (13MB) is not committed — fetch it on first run (needs yt-dlp).
if [ ! -f "$BENCH_DIR/jfk-rice.mp4" ]; then
  echo "Downloading jfk-rice.mp4 (JFK Rice University speech, 60-240s section)..."
  yt-dlp --download-sections '*60-240' -f 'bv*[height<=480]+ba/b[height<=480]' \
    --merge-output-format mp4 -o "$BENCH_DIR/jfk-rice.mp4" \
    'https://www.youtube.com/watch?v=WZyRbnpGyzQ' || echo "WARN: jfk-rice download failed; that video will be skipped"
fi

# slug|path — edit to point at your own copies of the material.
VIDEOS=(
  "jensen-gtc|$HOME/Projects/kanisleo-brand/crv-pro/reel-rebuild/jensen/jen_clip.mp4"
  "jensen-reel-zh|$HOME/Projects/kanisleo-brand/crv-pro/media/crv-reel-jensen-ZH.mp4"
  "screen-demo-zh|$HOME/Projects/kanisleo-brand/crv-pro/media/demo-zh.mp4"
  "jfk-rice|$BENCH_DIR/jfk-rice.mp4"
  "nasa-launch|$HOME/Projects/kanisleo-brand/crv-pro/reel-rebuild/nasa/launch.mp4"
  "nasa-earth|$HOME/Projects/kanisleo-brand/crv-pro/reel-rebuild/nasa/earth.mp4"
  "magic-diary-writing|$HOME/Projects/magic-diary/marketing/clips/clip-E-流暢書寫hero.mp4"
)

now() { perl -MTime::HiRes=time -e 'printf "%.2f\n", time'; }

run_one() { # slug method cmd... ; counts jpgs in $FRAME_DIR afterwards
  local slug="$1" method="$2"; shift 2
  local t0 t1 dt n
  t0=$(now)
  "$@" > "$WORK/$slug/$method.log" 2>&1
  local rc=$?
  t1=$(now)
  dt=$(perl -e "printf '%.1f', $t1-$t0")
  n=$(find "$FRAME_DIR" -name '*.jpg' 2>/dev/null | wc -l | tr -d ' ')
  echo "$slug,$method,$n,$dt,$rc" >> "$RESULTS/$slug/stats.csv"
  echo "  $method: frames=$n time=${dt}s rc=$rc"
}

for entry in "${VIDEOS[@]}"; do
  slug="${entry%%|*}"; src="${entry#*|}"
  if [ ! -f "$src" ]; then echo "SKIP $slug — missing $src"; continue; fi
  echo "== $slug ($src)"
  rm -rf "$WORK/$slug"; mkdir -p "$WORK/$slug" "$RESULTS/$slug"
  echo "video,method,frames,seconds,exit" > "$RESULTS/$slug/stats.csv"

  FRAME_DIR="$WORK/$slug/A"; mkdir -p "$FRAME_DIR"
  run_one "$slug" A ffmpeg -y -hide_banner -i "$src" -vf fps=1 -q:v 2 "$FRAME_DIR/f_%04d.jpg"

  FRAME_DIR="$WORK/$slug/B"; mkdir -p "$FRAME_DIR"
  run_one "$slug" B ffmpeg -y -hide_banner -i "$src" -vf fps=0.5 -q:v 2 "$FRAME_DIR/f_%04d.jpg"

  FRAME_DIR="$WORK/$slug/C/frames"
  run_one "$slug" C crv "$src" --no-transcribe --overwrite -o "$WORK/$slug/C"

  FRAME_DIR="$WORK/$slug/D/frames"
  run_one "$slug" D crv "$src" --no-transcribe --adaptive --overwrite -o "$WORK/$slug/D"

  # keep the crv dedup lines for the report
  grep -hiE 'dedup|scene|frames' "$WORK/$slug/C.log" | tail -5 > "$RESULTS/$slug/crv-default.txt" || true
  grep -hiE 'dedup|scene|frames' "$WORK/$slug/D.log" | tail -5 > "$RESULTS/$slug/crv-adaptive.txt" || true
done

echo; echo "Done. Stats in $RESULTS/<slug>/stats.csv, frames in $WORK/<slug>/."
