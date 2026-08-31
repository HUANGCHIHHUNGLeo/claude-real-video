## 0.10.3 — 2026-08-31

- **The caption file's header no longer opens the transcript.** A platform
  `.vtt` starts with `WEBVTT` / `Kind: captions` / `Language: en`, and only
  the first of those was being dropped — so since 0.10.2 made captions the
  normal path for URL runs, every such `transcript.txt` began with two lines
  nobody said. Everything ahead of the first timecode is file header by spec,
  so that is what is skipped now; `NOTE`, `STYLE` and any header key added
  later are covered too, and cue text is untouched.

## 0.10.2 — 2026-08-28

- **URL downloads now use the platform's own captions** (#25, by @Daily-AC).
  The "existing subtitles" fast path only ever held for local files — a URL
  run never asked yt-dlp for captions and always fell through to Whisper,
  even when the platform had a transcript sitting right there. crv now reads
  the video's metadata once and asks for a **single exact language code**
  (preferring `--lang`, then the video's own language, then English; manual
  tracks before auto-generated) — not `--sub-langs all`, which on YouTube
  means 157 auto-translated tracks, and not a regex, which still matches
  them. Fail-open: any metadata failure just means Whisper runs as before.
- **A partial download no longer hands ffmpeg a subtitle file** (#25). The
  `source.*` fallback glob now screens out `.vtt`/`.srt`-style sidecars, which
  could previously be picked up as "the video" and die with no video stream.

## 0.10.1 — 2026-08-27

- **`--to` keeps the frame timestamps again** (#19, #21). The window's `-t` was
  an output-side option, so ffmpeg decoded past the window end and the
  showinfo log covered more frames than were written — the count mismatch
  silently threw away every timestamp (no `frames.json`, no
  `frame timestamps:` line). `-t` now sits on the input side with `-ss`.
- **A window now reaches shipped captions too** (#20, #23). Sidecar `.srt`/`.vtt`
  files and embedded subtitle streams are clipped to `--from`/`--to`, so a
  windowed run gets a windowed transcript whichever path produced it.
- **`--text-anchors` lands on the right frames under `--from`** (#20, #24).
  Anchor frame indices are rebased onto the window start — an input-side seek
  restarts ffmpeg's frame counter at zero, so source-clock cue times pointed
  `start x fps` frames too late.
- **A broken Pillow install fails loudly instead of silently skipping dedup**
  (#22). Pillow is a declared dependency; when it cannot import, the run now
  raises with a reinstall hint instead of producing `#19`'s exact signature
  (no `frames.json`, no timestamps, exit 0) from a different cause.

All four were reported — and three arrived as ready pull requests with
regression tests — by @Jassu225. Thank you.

## 0.10.0 — 2026-08-22

- **`--from` / `--to` analysis window** (#16): analyse a slice of a long video
  without re-encoding it first. The frame budget and the transcript follow the
  window; reported timestamps stay on the source clock.
- **`--frame-width`** (#17): control the extracted frame width (default 640).

## 0.9.3 — 2026-08-18

- **A failed ffmpeg no longer reads as an empty video** (#15). `extract_frames()`
  and `extract_frames_adaptive()` never checked ffmpeg's exit code, so a run
  whose ffmpeg invocation failed outright looked identical to a video with
  nothing to extract — `0 frames`, exit 0 on older versions, and a generic
  "no frames" error on newer ones. Frame extraction now raises with ffmpeg's
  actual stderr (`ffmpeg frame extraction failed (exit 8). ffmpeg said: …`)
  whenever ffmpeg exits non-zero and produced nothing, the same policy the
  whisper branch has always had. Thanks @HPoyisis for the precise report,
  the shim reproduction, and the fix suggestion.

## 0.9.2 — 2026-08-18

- **YouTube downloads work again out of the box.** YouTube now requires solving a
  JavaScript "n challenge" before serving video data; yt-dlp older than 2026.07 can't
  solve it, so URL inputs failed with `HTTP Error 403: Forbidden` or "n challenge
  solving failed". The dependency is now `yt-dlp[default,deno]>=2026.7.4`, which pulls
  in yt-dlp's official EJS challenge solver *and* a bundled Deno runtime — no system
  Node/Deno setup needed. Existing installs: `pip install -U claude-real-video` fixes it.

## 0.9.1 — 2026-08-17

- **ffmpeg 9.0 compatibility** (#14). ffmpeg 9.0 removed the long-deprecated `-vsync`
  option, so every extraction failed with "No frames could be extracted". crv now
  probes the installed ffmpeg once and uses `-fps_mode vfr` when available (ffmpeg
  5.1+), falling back to `-vsync vfr` on older builds. Thanks @volpatocode for the
  precise report.

## 0.9.0 — 2026-08-11

- **Memory across videos.** crv now keeps a local index of everything it has watched
  (transcript lines + on-screen text, timestamps included), so you can ask across your
  whole library instead of re-processing:

  ```bash
  crv-ask "pricing strategy"     # → which video, which second, the exact line
  crv-ask 定價                    # CJK works: trigram FTS + substring fallback
  crv-ask --list                 # everything you've watched, newest first
  crv-ask --prune 200            # keep the newest 200, reclaim the space
  ```

  Re-running the same source with the same options now says "already watched" and points
  at the existing analysis in 0.04s instead of re-processing (measured against 5.5s);
  different options or `--overwrite` re-analyse as before. Everything is local — one
  SQLite file at `~/.crv/memory.db`, user-only permissions, no embeddings, no network.
  First indexing prints a one-line notice; opt out entirely with `CRV_NO_MEMORY=1`.

- **MCP server: 2 tools → 5.** New: `search_memory` (ask across every watched video),
  `list_watched` (check before re-watching), `get_transcript` (words only, no frames —
  saves context when you don't need images). `watch_video` now indexes automatically.

- Hardened against review findings before release: FTS5 queries are injection-safe and
  verified literally after tokenizer fallback, empty queries and unbounded limits are
  rejected, the schema refuses to downgrade an index written by a newer build, migrations
  are atomic (no `executescript` inside the write lock), foreign keys are on, the DB file
  is chmod 600, and concurrent writers take `BEGIN IMMEDIATE` (6 simultaneous writers
  tested clean).

## 0.8.2 — 2026-08-08

- Pro pointer at the end of a run now shows current pricing ($29 one-time, launch code
  through Aug 31) instead of the expired founder price. Opt out with `CRV_NO_HINT=1`
  as before.

## 0.8.1 — 2026-08-03

- Registry metadata only: `mcp-name` marker in the README and a `server.json` for the official MCP Registry (registry.modelcontextprotocol.io). No code changes.

## 0.8.0 — 2026-08-02

- **MCP server.** `pip install 'claude-real-video[mcp]'` then `crv-mcp` — the crv pipeline over the Model Context Protocol, so Claude Desktop, Claude Code, Cursor and any MCP client can ask for a video to be watched. Two tools: `watch_video` (transcript + first batch of keyframes as inline images) and `get_frames` (page through the rest). Analyses cached per source under `~/.cache/crv-mcp`; frames are resized to 768px before returning so responses stay context-friendly. Verified end-to-end on Claude Code with a real model run.

## 0.7.19 — 2026-07-31

- **Fixed the broken images on the PyPI page.** The README pointed at `docs/…` with relative paths. GitHub resolves those; PyPI does not, so the demo poster, the animated demo and the contact-sheet example had all been rendering as broken-image icons on the package page — since at least 0.7.17, not just this release. They now use absolute `raw.githubusercontent.com` URLs, which render in both places.

## 0.7.18 — 2026-07-31

- **`--yt-dlp-arg`**: pass raw options straight through to yt-dlp, repeatable. Asked for by @IamBennyOuO (issue #12) for pre-production workflows where the working answer to YouTube's JS challenges changes week to week.

```bash
crv "<url>" --yt-dlp-arg=-S --yt-dlp-arg=res:1080
crv "<url>" --yt-dlp-arg=--remote-components --yt-dlp-arg=ejs:github
```

  Works on both paths: appended to the command line when the yt-dlp executable is used, parsed with yt-dlp's own parser when the Python API is used, so the accepted syntax is identical either way.

- **Docs corrected.** `turbo` was described in three different ways across the CLI help and the README — "large-v3 accuracy" in one place, "close to large-v2 accuracy" in another. Per the model card, turbo is a pruned and finetuned large-v3: much faster than `large`, with a minor quality trade-off. The "~8x the speed" figure was removed everywhere; it had no source — no turbo benchmark exists in this repo and OpenAI publishes no multiplier.

## 0.7.17 — 2026-07-29

Isolated installs (`pipx install` / `uv tool install`) could not fetch URLs at all — fixed by @IamBennyOuO (PR #11):

- yt-dlp and whisper have always been dependencies, so both are installed. But those installers expose only crv's own entry points on PATH, so `shutil.which("yt-dlp")` found nothing and crv stopped with "yt-dlp not found". URL downloads were dead for anyone who installed that way.
- crv now falls back to yt-dlp's Python API when the executable is absent, keeping the same cookie-retry order as the command-line path.
- whisper is probed with `importlib.util.find_spec` rather than PATH — and deliberately not imported, since that pulls in torch on every silent video.
- `--cookies-from-browser` specs are parsed with yt-dlp's own parser, so the accepted syntax stays identical to the CLI.

## 0.7.16 — 2026-07-21

Batch-hardening, ported from a 2,181-video field report against crv Pro:

- dedup: new "action channel" — a handful of 32x32 cells changing hard (>45/255) marks a frame as new regardless of percentage. Small-in-frame fast action is no longer deduplicated away (synthetic repro: 1/10 action frames survived -> 10/10).
- all ffprobe/ffmpeg output decoded with errors="replace" — Latin-1-ish metadata no longer crashes a run.
- --max-frames default now scales with duration: clamp(150, seconds*1.5, 600); explicit value still wins.
- --min-frame-interval added as an alias of --fps-floor; both help texts now say plainly it is seconds per frame.
- distribution: Claude Code plugin marketplace support (/plugin marketplace add HUANGCHIHHUNGLeo/claude-real-video).

## 0.7.8 (2026-07-15)
- The end-of-run Pro pointer now shows this run's real numbers (deduped visual-change count and changes/min) instead of a generic line — only when the video actually has them; static or very short videos keep the quiet one-liner. Opt out unchanged: `CRV_NO_HINT=1`.

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

