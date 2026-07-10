# viralsynth — analyse a viral video, generate a new one from its motion blueprint

`viralsynth` is built on top of `crv --motion`. It takes a viral video
(YouTube / TikTok / local file), extracts its **motion blueprint** — every shot's
camera move, the editing rhythm, the pacing curve — and uses that blueprint to
**generate a new video**:

- **`clone`** — remix the source (or other clips) into a fresh cut that *feels*
  like the viral video: same pacing, same camera language. It pulls segments
  whose motion matches each shot in the blueprint, so the result emulates the
  style with different (or re-cut) content.
- **`breakdown`** — a narrated teardown of the viral video: keyframes + camera-move
  annotations + an LLM-written narration explaining *why* each shot works.

Everything runs locally with ffmpeg. The LLM (Claude by default, pluggable) only
writes the on-screen copy and narration — the *structure* comes from the motion
analysis, not from the model guessing.

---

## Install

```bash
pip install "claude-real-video[motion,llm]"   # motion analysis + LLM layer
# or individually:
pip install "claude-real-video[motion]"       # cloning works with --llm none
pip install "claude-real-video[llm]"           # Claude/OpenAI for the copy
```

ffmpeg is still required (`brew install ffmpeg`).

---

## Quick start

```bash
# Clone a viral short's style into a new 1080x1920 remix
viralsynth "https://www.tiktok.com/@user/video/..." \
  --mode clone --topic "my morning routine" --out remix.mp4

# Or a narrated teardown of the viral video itself
viralsynth "https://youtu.be/..." \
  --mode breakdown --topic "why this edit works" --out teardown.mp4
```

`viralsynth` does the analysis for you (it runs `crv --motion` into
`<out>.crv`), then plans and renders. To skip re-analysis, point at an existing
`crv --motion` output:

```bash
viralsynth "<url-or-file>" --analyze-out crv-out --mode clone --topic "..."
```

---

## How it works

```
source video
   │  crv --motion  (scene-aware frames + camera/rhythm)
   ▼
motion.json  ──►  Blueprint (shots: camera move + duration + motion level,
   │                        rhythm: cuts/min + cuts-by-thirds, chapters)
   │
   ├─ clone ─► candidate pool: slide a window over the source (and --assets
   │            videos), classify each window's camera move + motion. For each
   │            blueprint shot, pick the best-matching segment (camera + motion
   │            + duration), retime/pad to the target duration, optionally
   │            emulate the camera move, then concatenate. LLM writes the
   │            on-screen captions.
   │
   └─ breakdown ─► for each blueprint shot, take a representative frame + an
                LLM-written one-liner on *why* the shot works, lay them as
                caption cards, concatenate. Optional --tts voiceover.
```

### Candidate pool (clone)
The pool is built by sliding a fixed window (`--pool-len`, default 3s) every
`--pool-step` seconds (default 3s) over the source video and any `--assets`
videos, classifying each window with the same motion pipeline. Tune these to
trade speed for match variety:

- short clips with fast cuts → `--pool-len 1.5 --pool-step 1.0`
- long talking-head video → `--pool-len 5 --pool-step 4`

### LLM
`--llm auto` (default) uses Claude if `ANTHROPIC_API_KEY` is set, else OpenAI if
`OPENAI_API_KEY` is set, else a local OpenAI-compatible endpoint
(`VIRALSYNTH_LLM_BASE_URL`), else the offline `none` provider (still produces
usable, if blunter, copy). Override with `--llm claude|openai|local|none` and
`--llm-model`.

---

## Options

| flag | default | meaning |
|---|---|---|
| `source` | – | viral video URL or local file |
| `-o, --out` | `viralsynth_out.mp4` | output video path |
| `--analyze-out` | – | reuse an existing `crv --motion` dir (must have `motion.json`) |
| `--mode` | `clone` | `clone` (style remix) or `breakdown` (narrated teardown) |
| `--topic` | `your topic` | theme/reframe for the generated video |
| `--assets` | – | extra video file(s)/folder(s) to pull segments from (source always included) |
| `--transcribe` | off | transcribe audio during analysis (needs whisper) |
| `--llm` | `auto` | `auto` / `claude` / `openai` / `local` / `none` |
| `--llm-model` | – | override the LLM model id |
| `--tts` | off | (breakdown) add voiceover via local TTS if available (`say`/`espeak`) |
| `--pool-step` | `3.0` | seconds between candidate-pool windows |
| `--pool-len` | `3.0` | candidate window length (seconds) |
| `--width` / `--height` | `1080` / `1920` | output resolution (vertical by default, for Shorts/Reels) |

---

## Output

- `<out>.mp4` — the generated video.
- `<out>.plan.json` — the blueprint→segment mapping (clone) or the per-shot
  narration plan (breakdown). Handy for debugging or feeding your own editor.

For `clone`, each selected segment is retimed/padded to the blueprint shot's
duration, so the new video inherits the viral video's cut cadence. Where a
matching segment's camera move differs from the target, a light emulation
(pan slide / zoom push / handheld jitter) is applied; if the emulation filter
ever fails, it falls back to a plain fit so the render always completes.

---

## Notes

- Everything runs locally; nothing is uploaded by the tool. Respect content
  rights — use videos you have permission to analyse and remix.
- The clone mode re-cuts existing footage; it does not generate new imagery. For
  fully synthetic footage, pair the blueprint with an image/video generator
  upstream and feed the result in via `--assets`.
- Offline (`--llm none`) copy is functional but blunt; a real LLM makes the
  captions and narration read naturally.
