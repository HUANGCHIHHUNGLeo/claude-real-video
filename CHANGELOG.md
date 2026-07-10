## 0.7.2 (2026-07-10)
- **Safer output directories**: running into a folder that already holds a previous analysis is now refused, so two videos can never mix frames or audio. Pass the new `--overwrite` flag to replace it (only crv's own artifacts are removed). Recommended: one folder per video.
- **Fail loudly on bad sources**: zero extracted frames now raises a clear error (incomplete download / not a playable video / check ffmpeg) instead of quietly producing an empty result; partial-download leftovers (`.part`/`.ytdl`/`.tmp`) are no longer picked up as the video.
- **Honest silent-video diagnosis**: a video with no audio track now says so, instead of telling you to install whisper.
- **Cleaner output**: the temporary 16kHz `audio.wav` used for transcription is removed after Whisper finishes (`--keep-audio`'s `audio.m4a` is untouched).
- **Windows fix**: `viewer.html` is read/written as UTF-8 explicitly — CJK content no longer crashes on cp1252.
- `__version__` now reports the installed package version.
- Docs: README install commands show the `[whisper]` extra (extras never auto-install), skill-install instructions clone the repo first, Options table lists all flags, and `--text-anchors` wording matches reality (sidecar/embedded subtitles only).

## 0.7.1 (2026-07-10)
- **Timestamped transcript**: every analysis now also writes `transcript.json` — the same transcript as per-line segments with start/end times (from Whisper segments, or the video's own subtitle cues when available). Pipe it into your own tools, or give your LLM timings instead of a wall of text.
- README: build-in-public link; crv-web footer credit.

