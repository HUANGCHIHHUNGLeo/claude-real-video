# claude-real-video — Use Case Guide (with `--motion`)

`claude-real-video` (the `crv` CLI) turns a video into something any LLM can read:
**scene-aware keyframes + a transcript**, all produced locally. Keyframes tell a
model *what* is on screen. The `--motion` flag adds *how* it moves — camera work
and pacing — because a stack of stills alone drops the two things that make video
video: motion and editing rhythm.

This guide covers installation, the motion features, and concrete workflows.

---

## 1. Install

```bash
# frames + dedup (core)
pip install claude-real-video

# + speech-to-text (recommended)
pip install "claude-real-video[whisper]"

# + motion analysis (camera moves, rhythm, bursts)
pip install "claude-real-video[motion]"

# everything
pip install "claude-real-video[whisper,motion]"
```

You also need **ffmpeg** on your `PATH` (`brew install ffmpeg` on macOS,
`sudo apt install ffmpeg` on Linux, `winget install Gyan.FFmpeg` on Windows).

> pip extras never install themselves — without `[whisper]` there is no
> transcription, and without `[motion]` the `--motion` / `--chapters` / `--poster`
> flags print a clean "OpenCV required" message instead of failing cryptically.

Verify:

```bash
crv --help | grep -E "motion|poster|chapters"
```

---

## 2. The motion features

| flag | what it adds |
|---|---|
| `--motion` | camera-move label per shot + editing-rhythm summary + 0.2s action-burst frames for high-motion shots. Writes `motion.json` too. |
| `--chapters` | auto chapter list from the shot boundaries, labelled by the transcript at each start. Implies `--motion`. |
| `--poster` | a single sharpest representative lead frame (`poster.jpg`). |
| `--motion-fps` | motion sampling rate (default `5.0`). Higher = more precise, slower. |
| `--burst-gap` | seconds between action-burst frames (default `0.2`). |
| `--max-burst-frames` | cap on burst frames per high-motion shot (default `12`). |
| `--high-motion-pct` | motion level (%W/s) above which a shot earns a burst (default `8.0`). |

All of it lands in `MANIFEST.txt` as plain text your LLM already reads:

```
--- motion analysis --
editing rhythm: 14 shots | 21.0 cuts/min | avg 2.8s (median 2.1s, range 0.8-9.4s)
cuts by thirds (open/middle/close): 7 / 4 / 3
shots:
  #01  0.00-2.10s  (2.10s) camera: pan-right   motion: high (12.3%W/s) burst: burst_shot01_1..4
  #02  2.10-4.80s  (2.70s) camera: zoom-in     motion: medium (3.1%W/s)
  #03  4.80-9.20s  (4.40s) camera: static      motion: low (0.2%W/s)
```

- **Camera-move labels**: `static`, `pan-left`, `pan-right`, `tilt-up`, `tilt-down`,
  `zoom-in`, `zoom-out`, `handheld`. Estimated from a global affine transform per
  frame pair (Shi-Tomasi features → Lucas-Kanade flow → partial-affine). A *pan*
  reads a consistent translation; *zoom* reads coherent scale with little
  translation; *handheld* reads lots of motion with no consistent direction
  (high direction variance); *static* reads near-zero motion.
- **Editing rhythm**: `cuts/min` = `(shots − 1) / duration × 60`. "cuts by thirds"
  counts how many shots *start* in the open / middle / close thirds — that's your
  pacing curve in three numbers.
- **Action bursts**: high-motion shots get extra `burst_shotNN_*.jpg` frames spaced
  `0.2s` apart, so the model sees a movement *as a sequence* instead of guessing
  what happened between two keyframes. They live in `frames/` alongside the normal
  keyframes, so `--grid` and `--viewer` pick them up automatically.

---

## 3. Use cases

### A. Creator studying why a viral video holds attention
You have a reference reel. You don't just want to know what's in it — you want to
know *why it works*: where the cuts land, whether the open hooks with a fast
edit, whether the close lingers.

```bash
crv "https://www.instagram.com/reel/XXXX/" \
  -o study/reel --motion --chapters --grid --why "why does this hold attention"
```

Then paste `MANIFEST.txt` + the grids into Claude/Gemini and ask:
> "The open third has 7 shots starting in 3 seconds. Which cuts are doing the
> work, and would a slower open test better? Back it with the numbers."

### B. Editor deconstructing a reference cut, shot by shot
You're reverse-engineering a music video or ad. You want the shot list as a
table you can rebuild.

```bash
crv reference.mp4 -o decon --motion --poster
```

`motion.json` gives you the structured shot list (start/end/camera/motion) to
drive your own timeline tool. Ask your LLM:
> "Rebuild this as an editing script: for each shot give me the camera move,
> duration, and whether it's a cut or a match-move."

### C. Feeding video to Claude, ChatGPT, Gemini, or a self-hosted model
The point of the tool: the model reads the folder, not the video file. For fast
motion, include the bursts.

```bash
crv "https://youtu.be/..." -o out --motion --grid
```

Drop into the chat:
- `MANIFEST.txt` (what + how),
- `grids/grid_*.jpg` (keyframe contact sheets — ~9 frames per image),
- `frames/burst_shotNN_*.jpg` for any high-motion shot you want the model to
  follow precisely.

Works identically for a local model (llama.cpp, Ollama, vLLM) — it just reads
the same text + images.

### D. Self-hosted / privacy-first
Everything runs locally. Nothing is uploaded by the tool. Pair with a
self-hosted model and you have an end-to-end local "watch this video" pipeline
with zero cloud dependency.

```bash
crv meeting_recording.mp4 -o local --no-transcribe --motion   # silent / no speech
crv meeting_recording.mp4 -o local --whisper-model small --motion
```

### E. Lead with the best frame
`--poster` writes `poster.jpg` — the sharpest, most informative keyframe — so the
model reads the strongest frame first instead of an arbitrary one.

```bash
crv lecture.mp4 -o lec --poster
```

---

## 4. How to read the result

```
crv-out/
  source.mp4        # the downloaded/copied video
  frames/           # scene-change keyframes (frame_001.jpg …)
                    #   + burst_shotNN_*.jpg action bursts (with --motion)
  grids/            # 3×3 contact sheets (with --grid)
  poster.jpg        # representative lead frame (with --poster)
  transcript.txt    # plain transcript (if audio/subtitles present)
  transcript.json   # timestamped segments
  motion.json       # structured camera/rhythm/chapters data (with --motion)
  MANIFEST.txt      # the single file to paste into an LLM
  viewer.html       # local browser viewer (with --viewer)
```

Read `MANIFEST.txt` first, then the grids, then individual burst frames only
when you need to follow one specific movement.

---

## 5. Tips & tuning

- **Fast-cut reel under-sampled?** Lower `--scene 0.15` to catch more cuts; the
  motion shot detection is independent and still finds boundaries.
- **Bursts too many / too few?** Tune `--high-motion-pct` (lower = more shots
  burst) and `--max-burst-frames`.
- **Motion analysis too slow on a long video?** Lower `--motion-fps` (e.g. `3.0`).
- **No speech?** Add `--no-transcribe` — much faster, motion still works.
- **Keep the analysis** in your notes: `--kb ~/notes` saves `MANIFEST.txt` as a
  dated markdown note.

Everything — frames, transcript, motion — is produced on your machine. What you
paste into an LLM afterwards is your choice.
