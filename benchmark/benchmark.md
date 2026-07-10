# crv extraction benchmark v1 — fixed-rate vs scene-aware frame extraction

A small, reproducible comparison of fixed-interval frame extraction (plain ffmpeg)
against crv's scene-aware + deduplicated extraction, across 7 videos of different
types. This is an experiment log, not a marketing page: it includes the cases
where crv loses, and the exact commands to rerun everything.

Scope: **frame extraction only.** Transcription was disabled (`--no-transcribe`)
in every run so Whisper time does not pollute the timings. Accuracy of crv's
downstream analysis (labels, shot detection) is *not* measured here — see
"Not covered yet".

## 1. Method

### Environment

| | |
|---|---|
| Machine | Mac mini, Apple M4, macOS 15.7.3 |
| ffmpeg | 7.1 |
| crv | sections 2-4: 0.7.3 (the run that found the dedup bug); section 5: 0.7.4 (the fix) |
| Python | 3.14 (Homebrew) |

### Methods compared (per video)

```
# A — fixed 1 fps
ffmpeg -i in.mp4 -vf fps=1 -q:v 2 out_%04d.jpg

# B — fixed 0.5 fps (one frame every 2 s)
ffmpeg -i in.mp4 -vf fps=0.5 -q:v 2 out_%04d.jpg

# C — crv default
crv in.mp4 --no-transcribe -o outdir

# D — crv adaptive scene detection
crv in.mp4 --no-transcribe --adaptive -o outdir
```

Runner: [`run_benchmark.sh`](run_benchmark.sh). Wall-clock time measured around
each command; frame counts are the number of JPEGs on disk afterwards.

### Test material

| # | slug | type | duration | resolution | source |
|---|------|------|----------|------------|--------|
| 1 | jensen-gtc | fast speaker + slides (en) | 150 s | 1280x720\@60 | GTC 2026 keynote clip (local file) |
| 2 | jensen-reel-zh | fast-cut vertical promo reel, text cards (zh/en) | 30 s | 1080x1920\@30 | local file |
| 3 | screen-demo-zh | screen recording / UI, text-heavy (zh) | 58 s | 1920x1080\@30 | local file |
| 4 | jfk-rice | historic speech, grainy single-shot footage (en) | 180 s | 480p | JFK Rice University speech, youtube.com/watch?v=WZyRbnpGyzQ, `yt-dlp --download-sections '*60-240'` |
| 5 | nasa-launch | high-speed action, rocket launch, no speech | 527 s | 1920x1080\@30 | NASA footage (local file) |
| 6 | nasa-earth | slow orbital pans, no speech | 201 s | 1280x720 | NASA ISS footage (local file) |
| 7 | magic-diary-writing | slow gradual handwriting animation | 52 s | 720x1560\@25 | product UI clip (local file) — chosen deliberately as a hard case for scene detection |

Videos 1-3 and 5-7 are local files from our own projects; swap the paths at the
top of `run_benchmark.sh` for your own material. Only #4 is downloadable as-is.

### Token estimate

`tokens ≈ frames × 765`, where 765 is the approximate Claude vision cost of one
~1.15-megapixel image ((width x height)/750). Frames here range from 480p to
1080p, so per-frame cost varies in practice; the flat 765 makes methods
comparable, not billing-accurate.

## 2. Results — all 7 videos x 4 methods

| video | A: 1 fps | B: 0.5 fps | C: crv default | D: crv --adaptive |
|---|---|---|---|---|
| | frames / s / ~tokens | frames / s / ~tokens | frames / s / ~tokens | frames / s / ~tokens |
| jensen-gtc (150 s) | 150 / 1.4 / 115k | 75 / 1.4 / 57k | **87 / 1.7 / 67k** | 101 / 3.1 / 77k |
| jensen-reel-zh (30 s) | 30 / 0.3 / 23k | 15 / 0.3 / 11k | 3 / 0.5 / 2.3k | 3 / 0.7 / 2.3k |
| screen-demo-zh (58 s) | 58 / 0.4 / 44k | 29 / 0.4 / 22k | 6 / 0.6 / 4.6k | 6 / 1.0 / 4.6k |
| jfk-rice (180 s) | 180 / 9.2 / 138k | 90 / 9.4 / 69k | **53 / 10.0 / 41k** | 116 / 18.9 / 89k |
| nasa-launch (527 s) | 527 / 9.3 / 403k | 264 / 9.1 / 202k | **20 / 10.0 / 15k** | 20 / 19.0 / 15k |
| nasa-earth (201 s) | 201 / 3.5 / 154k | 100 / 3.5 / 77k | **101 / 3.9 / 77k** | 101 / 7.4 / 77k |
| magic-diary-writing (52 s) | 52 / 0.2 / 40k | 26 / 0.2 / 20k | 3 / 0.4 / 2.3k | 3 / 0.6 / 2.3k |

Dedup stage numbers (from crv's own output, `kept (deduped from extracted)`):

| video | C default | D --adaptive |
|---|---|---|
| jensen-gtc | 87 from 152 | 101 from 190 |
| jensen-reel-zh | 3 from 32 | 3 from 34 |
| screen-demo-zh | 6 from 59 | 6 from 66 |
| jfk-rice | 53 from 180 | 116 from 333 |
| nasa-launch | 20 from 528 | 20 from 528 |
| nasa-earth | 101 from 201 | 101 from 204 |
| magic-diary-writing | 3 from 52 | 3 from 52 |

Bold in the main table marks the rows where a visual spot-check found the crv
output kept the content of the video; the non-bold crv rows are the failure
cases discussed below. Runtime: crv default costs roughly 0.3-0.8 s more than
plain 1 fps extraction on the same file; `--adaptive` roughly doubles crv's
runtime (two-pass comparison).

## 3. Per-video findings (visual spot-checks)

Representative frames for every claim are in `results/<slug>/`. Spot-checks were
done by eye on contact sheets of method A vs method C frames; they are samples,
not exhaustive audits.

### jensen-gtc — speaker + slides. crv adequate, modest win
87 frames vs 150 at 1 fps (42% fewer). Subsampled contact sheets
(`results/jensen-gtc/`) show the same beats in both: speaker, "NVIDIA and
Microsoft Reinvent PC" slide, Windows logo wall, moon-lander demo video, code
UI. No missed slide was found in the sampled sheets; not checked frame-by-frame.
Observed: many kept frames are near-identical speaker shots — a gesturing
speaker moves more than 8% of pixels, so dedup keeps him again and again.
Compression on talking-head material is therefore limited.

### jensen-reel-zh — fast-cut text-card reel. crv loses
crv kept 3 of 30 seconds: hook card, one mid screenshot, CTA card. The reel's
message is carried by ~5 distinct full-screen text cards; the 1 fps extraction
shows at least two cards that appear in **no** crv frame ("它自己看出每個鏡頭在拍什麼",
"連語氣和情緒的變化都被抓出來" — see `results/jensen-reel-zh/`). These are
caption-sized text swaps over a near-black static layout: well under the 8%
pixel-change dedup threshold. `--adaptive` did not change the result (3 frames).
`--text-anchors` is the intended flag for this failure mode but requires a
subtitle track, which this file does not have. An LLM reading crv's 3 frames
would miss roughly half the reel's claims.

### screen-demo-zh — screen recording. crv loses
6 frames from 58 s. The 1 fps run contains at least two states missing from all
6 crv frames: an embedded chart slide, and the final analysis screen *with its
five-bullet summary fully rendered* (crv's last frame catches the headline
before the bullets appear — the most information-dense state of the whole demo
is absent). Text filling into a fixed dark layout is exactly what the dedup
comparator cannot see. Same `--text-anchors` caveat as above (no subtitle track
in a raw screen recording).

### jfk-rice — grainy 1962 footage, single podium shot. crv default wins, --adaptive backfires
Default: 53 frames from 180 — reasonable, though the footage is one continuous
podium shot and even 53 frames are visually redundant (sheet in
`results/jfk-rice/`). `--adaptive`: 116 frames from 333 extracted — more than
double the tokens for no new visual content that we could find in the sheets.
On noisy low-quality footage the adaptive detector appears to fire on grain and
compression shimmer. Observed: do not use `--adaptive` on old noisy material.

### nasa-launch — 8.8 min launch. crv's best case in this set
20 frames instead of 527 (96% fewer, ~403k → ~15k estimated tokens). The
contact sheet of all 20 (`results/nasa-launch/`) reads as a complete story:
pad, ignition, liftoff, ascent, plume drift, empty pad, fade to dark. The long
smoke-drift minutes collapse to a handful of frames. No missed event was found
in the 1 fps sample we checked against, with the caveat that "event" is
loosely defined for footage of smoke.

### nasa-earth — slow orbital pans. crv ≈ 0.5 fps, no advantage
101 frames vs 201 at 1 fps — on continuously changing slow footage crv behaves
like a ~0.5 fps sampler (every pan crosses the 8% threshold within ~2 s).
Coverage is good and diverse, but method B gets the same frame count for less
compute. `--adaptive` changed nothing (101).

### magic-diary-writing — handwriting animation. Designed to break crv; it does
Default: 3 frames — white flash, blank page, finished page. The entire writing
progression (the actual content of the clip) is collapsed; from crv's output an
LLM cannot even tell this is a writing animation rather than a hard cut.
**`--adaptive`, the flag meant for slow morphs, did not help: still 3 frames.**
The extraction stage is not the bottleneck — dedup is: we measured
`--dedup-threshold 1` → 5 frames, `0.5` → 5, and `--dedup-threshold 0` → still 5.
The dedup comparator works on a 16x16 downscaled signature with a per-channel
tolerance of 25/255 (`core.py, dedup_frames`); thin ink strokes on a large page
change zero downscaled pixels beyond tolerance, so consecutive frames measure
as *exactly 0.0% different* and are dropped at any threshold. The 5 frames that
`--dedup-threshold 1` recovers do show a usable blank → quarter → half →
three-quarters → full progression (`results/magic-diary-writing/`), which is
arguably a fair summary — but there is currently **no flag combination** that
returns the fine-grained progression a fixed 1 fps trivially captures.

## 4. Where crv wins / where crv loses

### Wins (measured in this set)
- Long real-world footage with redundant stretches: nasa-launch 527 → 20 frames
  (96% token reduction) with the narrative arc intact on visual inspection.
- Old single-shot footage, default settings: jfk-rice 180 → 53.
- Speaker + slides: jensen-gtc 150 → 87 with the same sampled beats.
- Runtime overhead over plain ffmpeg is small in default mode (≤ ~1 s extra on
  these files).

### Losses / needs flags (measured in this set)
- **Meaning that changes faster than pixels**: text cards (jensen-reel-zh) and
  screen recordings (screen-demo-zh) lose key states. `--text-anchors` targets
  exactly this but requires a subtitle track — both failing files have none.
  Lowering `--dedup-threshold` helps only until the 16x16 signature floor.
- **Slow thin-stroke morphs** (magic-diary-writing): collapsed to 3 frames and
  no current flag fully recovers the progression; the 16x16/tol-25 dedup
  signature is blind to sub-signature changes, so even `--dedup-threshold 0`
  keeps only 5. This is an architectural limit of the current dedup, not a
  tuning issue.
- **`--adaptive` on grainy footage backfires**: jfk-rice 53 → 116 frames
  (+119% tokens) with no new content found. Adaptive also changed nothing on
  the three videos it was expected to help (earth, launch, writing — identical
  frame counts to default), because the extra extracted candidates are then
  removed again by the same dedup stage.
- **Talking-head compression is limited**: a gesturing speaker defeats dedup
  (jensen-gtc keeps many near-identical shots).

## 5. v0.7.4 dedup fix — before/after

Sections 2-4 above are the v0.7.3 run, kept unchanged as the "before". They
caught a real bug: the dedup comparator (16x16 signature, tolerance 25/255)
measured thin ink strokes, caption/text-card swaps and local UI updates as
*exactly 0.0% difference* — so `--dedup-threshold 0` could not recover them
(section 3, magic-diary-writing). v0.7.4 adds a second, *settled-local*
detector next to the unchanged global one: on a 192px signature it looks for a
region that differs strongly (>80/255) from every kept frame in the window —
with ±1px shift tolerance so film weave/grain/jitter can re-match, and a
stricter 105/255 second pass so soft-contrast drift (smoke) fades out — and
that is *not still changing* toward the next frame: a settled new state, not
motion mid-flight. It only runs when the scene is otherwise static (<3% global
diff vs the previous frame, or the final frame), and a cooldown (bar raised ~2x after
each settled keep, decaying 0.7/frame) stops continuously-"settling" motion
(a waving flag pausing every second) from taking a frame each time.

Same machine, same files, crv 0.7.4, default mode (C) and `--adaptive` (D):

| video | C before (0.7.3) | C after (0.7.4) | Δ time (C) | what changed |
|---|---|---|---|---|
| magic-diary-writing | 3 from 52 | **9 from 52** | 0.4 → 0.7s | writing progression now visible (blank → four intermediate states → full page); before: blank + finished only. `results/magic-diary-writing/crv-0.7.4-all-9-frames.jpg` |
| jensen-reel-zh | 3 from 32 | **8 from 32** | 0.5 → 0.6s | all 5 caption cards present, incl. the 2 previously lost ("它自己看出…", "連語氣和情緒…"). `results/jensen-reel-zh/crv-0.7.4-all-8-frames.jpg` |
| screen-demo-zh | 6 from 59 | **15 from 59** | 0.6 → 0.8s | the chart slide and the final five-bullet summary (previously both missing) are in. `results/screen-demo-zh/crv-0.7.4-all-15-frames.jpg` |
| jfk-rice | 53 from 180 | 77 from 180 | 10.0 → 10.0s | +45%: the settled detector fires on real pose/flag changes that momentarily hold still on this grainy single-shot footage. Grain itself does not trigger (the shift-tolerant mask eats it); this is the price of local sensitivity, capped by the cooldown. |
| nasa-launch | 20 from 528 | 28 from 528 | 10.0 → 13.0s | +8 frames, all in the ignition/liftoff sequence (the most information-dense part); the smoke-drift minutes still collapse. Still 95% below 1 fps. |
| nasa-earth | 101 from 201 | 109 from 201 | 3.9 → 4.4s | +8 on slow pans; behaviour effectively unchanged. |
| jensen-gtc | 87 from 152 | 90 from 152 | 1.7 → 1.9s | +3; effectively unchanged. |

Notes:
- **The failure trio is fixed** (writing, text cards, screen recording) — the
  three cases section 3 called architectural limits — at the cost of moderate
  frame growth on grainy/high-motion footage (jfk +45%, still 57% below 1 fps).
- **Runtime**: the settled detector adds ~0-3s on these files (biggest on
  nasa-launch: 10 → 13s for an 8.8-min video). It only computes when the coarse
  channel says "duplicate" *and* the scene is static, so fast-cut material
  pays almost nothing.
- **`--adaptive` on grainy footage still backfires and is now worse**: jfk-rice
  D went 116 → 150 (extraction feeds 333 candidates; the settled channel keeps
  more of them). The section-3 advice stands: don't use `--adaptive` on old
  noisy material.
- The old `--dedup-threshold 1/0.5/0` probes from section 3 are obsolete: the
  settled channel scales with `--dedup-threshold` (gate = 0.85 x threshold), so
  lowering the threshold now genuinely recovers more local detail instead of
  hitting the 0.0% floor.

## 6. Not covered yet (in progress)
- Downstream answer accuracy: does an LLM answer questions better/equally from
  crv frames vs 1 fps frames? (The token numbers here only bound the cost side.)
- Any form of labelled ground truth, precision/recall of scene boundaries, or a
  confusion matrix for kept/dropped decisions.
- Transcription quality and speed (disabled in all runs here).
- More languages and more content types (sports, animation, dashcam).
- `--text-anchors` on files that *do* have subtitle tracks — the two failure
  cases above need a with-subtitles rerun to test the intended mitigation.
- Statistical rigour: single run per cell; timings on a warm disk cache.

## Reproducing

```
cd benchmark
./run_benchmark.sh            # frames land in ./work, stats in ./results
```

Edit the `VIDEOS` list in the script for your own material. The JFK clip:

```
yt-dlp --download-sections '*60-240' -f 'bv*[height<=480]+ba/b[height<=480]' \
  --merge-output-format mp4 -o jfk-rice.mp4 'https://www.youtube.com/watch?v=WZyRbnpGyzQ'
```
