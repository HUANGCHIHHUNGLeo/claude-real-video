---
name: claude-real-video-for-agents
description: "Install and use crv (claude-real-video) — a tool that lets any AI agent watch videos by extracting scene-aware keyframes, deduplicating them, and transcribing audio. Use when the user shares a video URL or file and wants it analyzed, summarized, or discussed."
---

# claude-real-video for AI agents

## What is crv?

`crv` (claude-real-video) is a CLI tool that extracts meaningful frames and transcripts from videos so AI agents can "see" and "read" them. It uses scene-change detection (not fixed-interval sampling), sliding-window deduplication, and optional Whisper transcription.

**Key advantage**: Same 58-second clip at fixed 1fps = 58 frames. crv keeps the **26 that actually differ**, and `--grid` packs them into **3 contact sheets**. Fewer tokens, nothing missed.

## Installation

### Prerequisites

- Python 3.10+
- ffmpeg / ffprobe on PATH

```bash
# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

### Install crv

```bash
# Core (frames + dedup)
pip install claude-real-video

# With audio transcription support
pip install "claude-real-video[whisper]"
```

### Verify installation

```bash
crv --help
ffmpeg -version
```

### Install as agent skill

Run the bundled installer to symlink this skill into all detected agent platforms:

```bash
bash install-skill.sh
```

Or manually copy to your agent's skill directory:

```bash
# Claude Code
cp -r skills/claude-real-video-for-agents ~/.claude/skills/

# Codex
cp -r skills/claude-real-video-for-agents ~/.codex/skills/

# OpenCode
cp -r skills/claude-real-video-for-agents ~/.opencode/skills/

# Gemini CLI
cp -r skills/claude-real-video-for-agents ~/.gemini/skills/
```

## Usage

### Basic: Watch a video from URL

```bash
crv "https://www.youtube.com/watch?v=VIDEO_ID"
```

Output in `crv-out/`:
- `frames/` — deduplicated keyframes
- `transcript.txt` — plain-text transcript
- `MANIFEST.txt` — summary for LLM consumption

### Recommended: With grid and intent

```bash
crv "https://youtu.be/VIDEO_ID" -o crv-out --grid --why "what the user wants to know"
```

- `--grid` — tiles frames into 3x3 contact sheets (cuts image count ~9x)
- `--why` — focuses the analysis on a specific question

### Local file with transcript

```bash
crv lecture.mp4 -o out --lang en
```

### Frames only (no transcription — much faster)

```bash
crv clip.mp4 --no-transcribe
```

### Login-gated video

```bash
crv "https://..." --cookies cookies.txt
crv "https://..." --cookies-from-browser chrome
```

### Slow-changing content (animations, tutorials)

```bash
crv tutorial.mp4 --adaptive
```

### Save to knowledge base

```bash
crv "https://youtu.be/..." --why "pricing strategy" --kb ~/notes
```

### View what the model will see

```bash
crv video.mp4 --viewer
# Opens viewer.html — video + keyframes + transcript, fully offline
```

## Agent Workflow

When a user shares a video (URL or file path):

1. **Run crv** with `--grid` and `--why`:
   ```bash
   crv "<url-or-path>" -o crv-out --grid --why "<user's question>"
   ```
   For long videos, cap frames: `--max-frames 60`

2. **Read `MANIFEST.txt` first** — it lists every frame with timestamps and includes the transcript.

3. **Read contact sheets** in `crv-out/grids/` (each is a 3x3 sequence of consecutive keyframes, chronological). Only read individual `crv-out/frames/*.jpg` when you need a close-up.

4. **Answer the user's question**, citing timestamps from the manifest.

## CLI Reference

| Flag | Default | Description |
|---|---|---|
| `source` (positional) | — | Video URL or local file path |
| `-o, --out` | `crv-out` | Output directory |
| `--scene` | `0.30` | Scene-change sensitivity (0-1, lower = more frames) |
| `--fps-floor` | `1.0` | Guarantee at least one frame every N seconds |
| `--max-frames` | `150` | Hard cap on total frames |
| `--adaptive` | off | Adaptive scene detection for slow-changing content |
| `--lang` | `auto` | Whisper language (`en`, `zh`, `auto`, etc.) |
| `--cookies` | — | Netscape cookie file for login-gated sources |
| `--cookies-from-browser` | — | Read cookies from browser (`chrome`, `safari`, `firefox`, `edge`) |
| `--no-transcribe` | off | Skip audio transcription |
| `--viewer` | off | Write a local `viewer.html` |
| `--whisper-model` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `--dedup-threshold` | `8` | % of pixels that must change for a new frame |
| `--dedup-window` | `4` | Compare against last N kept frames |
| `--report` | off | Keep dropped frames + write `report.html` |
| `--why` | — | Viewing intent string, written into MANIFEST.txt |
| `--grid` | off | Tile frames into 3x3 contact sheets |
| `--kb` | — | Save as dated markdown note to knowledge-base folder |
| `--keep-audio` | off | Save full original soundtrack as `audio.m4a` |

## Python API

```python
from claude_real_video import process

result = process("https://youtu.be/...", "out", lang="en")
print(result.frame_count, result.transcript_path)
```

## Output Structure

```
crv-out/
├── MANIFEST.txt         # Summary for the LLM
├── frames/              # Deduplicated keyframes
├── transcript.txt       # Plain-text transcript
├── grids/               # 3x3 contact sheets (with --grid)
├── audio.m4a            # Full soundtrack (with --keep-audio)
├── viewer.html          # Local viewer (with --viewer)
├── report.html          # Dedup report (with --report)
└── dropped/             # Dropped frames (with --report)
```

## Tips for Agents

- Always use `--grid` — it dramatically reduces token usage while preserving visual continuity.
- Always use `--why` — it focuses the analysis on what the user actually cares about.
- Use `--max-frames 60` for long videos (>10 min) to stay within context limits.
- Use `--no-transcribe` when the user only cares about visuals (thumbnails, UI, slides).
- Use `--keep-audio` when the user asks about music, tone, or sound effects.
- Use `--adaptive` for screencasts, tutorials, or slow-moving content.
- Read `MANIFEST.txt` before frames — it has timestamps and context.
- Cite timestamps in your answers (e.g., "At 0:42, the presenter shows...").

## Notes

- Everything runs locally; nothing is uploaded by the tool itself.
- Re-running overwrites the output directory.
- Only download content you have the right to access.
- The `--cookies` option is for your own authorized access.
