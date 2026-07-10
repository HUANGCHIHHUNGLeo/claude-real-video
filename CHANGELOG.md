## 0.8.0 (2026-07-10)
- **`--motion`: camera-move classification + editing rhythm + action bursts.** Everything runs locally with ffmpeg + OpenCV (new `[motion]` extra — `pip install "claude-real-video[motion]"`), no ML models, no cloud.
  - **Camera-move classification** — every shot labelled `static` / `pan-left` / `pan-right` / `tilt-up` / `tilt-down` / `zoom-in` / `zoom-out` / `handheld`, estimated from a global affine transform (Shi-Tomasi + Lucas-Kanade + partial-affine) per motion-frame pair.
  - **Editing rhythm** — full shot list with durations, cuts/min, and how pacing shifts across the open/middle/close thirds, all as plain text in `MANIFEST.txt`.
  - **Action bursts** — high-motion shots automatically get 0.2s-apart frame sequences (`burst_shotNN_*.jpg`) so the model reads movement as a progression instead of guessing between keyframes.
  - **`motion.json`** — the same data structured, for your own tools.
- **`--chapters`** — derive an auto chapter list from the shot boundaries, labelled by the transcript text at each chapter start (written into `MANIFEST.txt` and `motion.json`). Implies the motion pipeline.
- **`--poster`** — pick the sharpest, most-informative kept frame as a representative lead frame (`poster.jpg`) so the model reads the best frame first.
- README: install commands list the `[motion]` extra; new "Motion" section with real sample output; Options table lists all new flags; Pro section reframed around the perception timeline + breakdown report.
- Skills: `claude-real-video/SKILL.md` documents `--motion` / `--chapters` / `--poster`.

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

