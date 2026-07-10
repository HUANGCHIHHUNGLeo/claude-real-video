---
name: viralsynth
description: "Analyze a viral YouTube / TikTok / Instagram video and generate a new video from its editing blueprint. Use when the user wants to study why a short went viral, clone/remix a viral video's style (camera moves + pacing) into a new cut, or make a narrated teardown/breakdown of it. Built on top of crv --motion (run `crv` first, or let this skill do it)."
---

# viralsynth — analyse a viral video, generate a new one

`viralsynth` turns a viral video's **motion blueprint** (per-shot camera moves +
editing rhythm, from `crv --motion`) into a new video. Two modes:

- **`clone`** — remix the source (or other clips) into a fresh cut that *feels*
  like the viral video: it pulls segments whose motion matches each shot in the
  blueprint and retimes them to the viral video's pacing. Same structure, new
  (or re-cut) content.
- **`breakdown`** — a narrated teardown: each shot becomes a keyframe + camera-move
  annotation + an LLM-written one-liner on *why* it works.

Everything runs locally (ffmpeg). The LLM (Claude by default, pluggable) only
writes captions/narration — the structure comes from the motion analysis.

## When to use

The user gives you a video URL (or local file) and asks to:
- "clone / remix / make one like this", "recreate this style", "make a video in
  the style of this reel"
- "break this down", "why is this viral", "analyse why this edit works", "make a
  teardown of this video"
- study pacing / camera language of a reference video

## Requirements

- Python 3.10+, ffmpeg on PATH (`brew install ffmpeg`)
- `pip install "claude-real-video[motion,llm]"` (gives both `crv` and `viralsynth`)
- For natural captions/narration: `ANTHROPIC_API_KEY` (Claude), else `OPENAI_API_KEY`,
  else a local OpenAI-compatible endpoint (`VIRALSYNTH_LLM_BASE_URL`). Without any,
  it still runs with a blunter offline copy (`--llm none`).

## Steps

1. Decide the mode from the user's wording: **clone** for "make one like this /
   remix", **breakdown** for "explain / teardown". Default to `clone`.

2. Run the automation. It analyses the video (via `crv --motion`) and renders in
   one command:

   ```bash
   viralsynth "<url-or-path>" --mode clone --topic "<what the new video is about>" -o remix.mp4
   # or
   viralsynth "<url-or-path>" --mode breakdown --topic "<focus of the teardown>" -o teardown.mp4
   ```

   To reuse an existing `crv --motion` output and skip re-analysis:

   ```bash
   viralsynth "<url-or-path>" --analyze-out crv-out --mode clone --topic "..."
   ```

3. Report the result: the output video path, how many segments/shots it used, and
   the pacing it inherited (cuts/min from the blueprint). The plan JSON
   (`<out>.plan.json`) lists the blueprint→segment mapping (clone) or the
   per-shot narration (breakdown).

4. If the user wants natural language copy, ensure an LLM key is set and re-run
   without `--llm none`. If they want more remix variety on a fast-cut video, add
   `--pool-len 1.5 --pool-step 1.0`.

## Key flags

| flag | default | meaning |
|---|---|---|
| `source` | – | viral video URL or local file |
| `-o, --out` | `viralsynth_out.mp4` | output video path |
| `--mode` | `clone` | `clone` (style remix) or `breakdown` (narrated teardown) |
| `--topic` | `your topic` | theme/reframe for the generated video |
| `--assets` | – | extra video file(s)/folder(s) to pull segments from (source always included) |
| `--analyze-out` | – | reuse an existing `crv --motion` dir (must have `motion.json`) |
| `--llm` | `auto` | `auto`/`claude`/`openai`/`local`/`none` |
| `--tts` | off | (breakdown) add voiceover via local TTS if available |
| `--pool-step` / `--pool-len` | `3.0` / `3.0` | candidate-pool window spacing/length (seconds) |
| `--width` / `--height` | `1080` / `1920` | output resolution (vertical by default) |

## How it works (so you can explain it)

```
source → crv --motion → motion.json (Blueprint: per-shot camera move + duration,
                                    rhythm: cuts/min + cuts-by-thirds)
  clone      → candidate pool: slide a window over the footage, classify each
               window's camera move + motion; for each blueprint shot pick the
               best-matching segment, retime/pad to its duration, concatenate.
  breakdown  → per shot: representative frame + camera-move label + LLM one-liner
               as caption cards, concatenated. Optional --tts voiceover.
```

## Notes

- Everything runs locally; nothing is uploaded by the tool.
- **Respect content rights** — only analyse/remix videos the user has permission
  to use. The clone mode re-cuts existing footage; it does not generate new imagery.
- For fully synthetic footage, pair the blueprint with an image/video generator
  upstream and feed the result in via `--assets`.
- Offline (`--llm none`) copy is functional but blunt; a real LLM reads naturally.
- If analysis fails on a login-gated site, the underlying `crv` accepts
  `--cookies cookies.txt` or `--cookies-from-browser chrome`.
