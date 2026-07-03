---
name: claude-real-video
description: Watch a video for the user. Use when the user shares a video URL (YouTube etc.) or local video file and wants it summarized, analyzed, or discussed — Claude can't ingest video directly, so this skill extracts scene-aware keyframes + transcript first, then reads those.
---

# claude-real-video — let Claude actually watch a video

## When to use

The user gives you a video (URL or file path) and asks what's in it, to summarize it, to analyze its structure, or to answer questions about it.

## Requirements

- `pip install claude-real-video` (installs the `crv` CLI; needs Python 3.10+ and ffmpeg)
- First transcription downloads a faster-whisper model automatically

## Steps

1. Run the extractor (add `--grid` to cut image count ~9x — recommended):

   ```bash
   crv "<url-or-path>" -o crv-out --grid --why "<what the user wants to know>"
   ```

   For long videos cap the frames: `--max-frames 60`.

2. Read `crv-out/MANIFEST.txt` first — it lists every frame with timestamps and includes the transcript.

3. Read the contact sheets in `crv-out/grids/` (each is a 3×3 sequence of consecutive keyframes, in chronological order). Only read individual `crv-out/frames/*.jpg` when you need a close-up of one moment.

4. Answer the user's question, citing timestamps from the manifest.

## Notes

- Everything runs locally; nothing is uploaded by the tool itself.
- If the video has no speech or transcription is unnecessary, add `--no-transcribe` (much faster).
- `--kb <dir>` saves a digest into a knowledge-base folder if the user wants to keep notes.
