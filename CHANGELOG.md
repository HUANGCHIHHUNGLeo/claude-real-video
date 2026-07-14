## 0.7.7 (2026-07-15)
- **faster-whisper support — new `[fast]` extra.** `pip install 'claude-real-video[fast]'` and crv automatically transcribes in-process with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2): same model names, same `transcript.txt` + `transcript.json` output, several times faster and lighter on RAM than the whisper CLI. No new flags — if the package is importable it's used, and any failure falls back to the `whisper` CLI automatically.
- The "install whisper" hint shown when no transcriber is present now mentions both options.

## 0.7.6 (2026-07-13)
- **Per-frame source timestamps — `frames.json`** (issue #7). Every kept `frame_XXX.jpg` now knows exactly which second of the original video it came from, surviving extraction, deduplication, `--max-frames` thinning and renaming. A machine-readable `frames.json` is written next to the frames: `{"file", "timestamp_sec", "timestamp", "selection_reason"}` — so you can cite visual evidence with a timestamp, align frames with `transcript.json` segments, or feed the mapping into video-RAG / lecture-note pipelines.
- Timestamps come from ffmpeg's `showinfo` log on the same select pass (no extra decode pass, VFR-accurate); the adaptive extractor gets them the same way. If the log and the extracted files ever disagree in count, crv writes no timestamps rather than wrong ones.
- `viewer.html` shows each keyframe's `MM:SS.mmm` on its cell, and the lightbox gains "play video from here" — click a keyframe, jump the player to that exact moment.
- `MANIFEST.txt` points the reading LLM at `frames.json` so reports can cite `[frame_012 @ 00:03:41.2]` instead of "somewhere in the middle".

## 0.7.4 (2026-07-11)
- **Dedup was blind to local change — fixed.** Benchmarking (benchmark/benchmark.md) caught the old comparator — a 16x16 downscaled signature with a 25/255 per-channel tolerance — measuring thin pen strokes, caption/text-card swaps and small UI updates as *exactly 0.0% difference*, so it dropped them at any `--dedup-threshold`, including 0. Measured damage: a handwriting clip collapsed 52 frames to 3 (blank page + finished page, no progression), a text-card reel lost 2 of its 5 caption cards, and a screen recording lost its most information-dense final state.
- The fix adds a second, *settled-local* detector next to the (unchanged) global one: on a finer 192px signature it looks for a region that differs strongly from every recent kept frame — with 1px shift tolerance so film grain/jitter don't trigger, and a stricter second tolerance pass so soft-contrast drift (smoke, clouds) doesn't — and that is *no longer changing* toward the next frame: a settled new state, not motion mid-flight. A cooldown stops continuously-"settling" motion (a waving flag pausing every second) from taking a frame each time. Full derivation and before/after numbers: benchmark/benchmark.md.
- **Default behavior changes**: content the old dedup was blind to now produces more frames (that's the point). On the benchmark set: handwriting clip 3 → 9 frames (progression visible), text-card reel 3 → 8 (all 5 cards present), screen demo 6 → 15 (final summary state included), JFK 1962 footage 53 → 77 (+45%, real settled pose changes on grainy film — the cost of the fix, kept in check by the cooldown), NASA launch 20 → 28 (ignition/liftoff sequence now sampled more densely), slow orbital pan 101 → 109, speaker+slides 87 → 90. Runtime on the 8.8-min launch video: +3s (10 → 13s end to end).
- Package metadata could report a stale version (e.g. 0.4.0) on editable installs made before the version bump — the dist-info was generated at install time and never refreshed. `__init__.py`'s fallback is now kept in sync with `pyproject.toml`; if `crv --version`-style checks show an old number on an editable install, re-run `pip install -e .` to regenerate the metadata.
- `report.html` now labels frames kept by the settled-local detector with their settled-change %.
- benchmark: `run_benchmark.sh` now downloads the JFK test clip via yt-dlp instead of shipping a 13MB mp4 in the repo; added a "v0.7.4 dedup fix — before/after" section to benchmark.md.

- Note: the final frame is exempt from the "scene has settled" motion check (the closing state of a video is always considered), but still has to pass both contrast gates.

## 0.7.3 (2026-07-10)
- `--whisper-model` now accepts `turbo` (close to large-v2 accuracy at ~8x the speed; needs openai-whisper>=20240930). Default stays `base` for fast first runs; sharper transcripts are one flag away.
- Transcription failures now print whisper's actual error instead of a silent "(none — transcription failed)".

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

