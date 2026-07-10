"""viralsynth — turn a viral video's motion blueprint into a new video.

Two modes:
  - clone     : remix the source (or other clips) into a fresh cut that *feels*
                like the viral video — same pacing, same camera language — by
                pulling segments whose motion matches each shot in the blueprint.
  - breakdown : a narrated teardown of the viral video (keyframes + camera-move
                annotations + an LLM-written narration), for teaching *why* it works.

All rendering is local ffmpeg. The LLM (pluggable, see llm.py) only writes the
on-screen copy and narration; the structure comes from the motion analysis.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .llm import get_llm, _CAMERA_WORDS


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


# --------------------------------------------------------------------------
# Blueprint
# --------------------------------------------------------------------------

class Blueprint:
    def __init__(self, source_video: str, shots: list[dict], rhythm: dict,
                 chapters: list[dict], transcript: list[dict]):
        self.source_video = source_video
        self.shots = shots
        self.rhythm = rhythm
        self.chapters = chapters
        self.transcript = transcript

    @property
    def duration(self) -> float:
        if not self.shots:
            return 0.0
        return max(s["end"] for s in self.shots)


def load_blueprint(out_dir: str) -> Blueprint:
    """Read crv's motion.json + transcript.json (from `crv --motion`) and locate
    the analysed source video."""
    mj = os.path.join(out_dir, "motion.json")
    if not os.path.exists(mj):
        raise RuntimeError(
            f"No motion.json in {out_dir}. Run `crv <video> --motion` first "
            "(the blueprint comes from the motion analysis).")
    data = json.load(open(mj, encoding="utf-8"))
    tj = os.path.join(out_dir, "transcript.json")
    segs = []
    if os.path.exists(tj):
        try:
            segs = json.load(open(tj, encoding="utf-8")).get("segments", [])
        except Exception:
            segs = []
    src = None
    for cand in ("source.mp4", "source.mkv", "source.webm"):
        p = os.path.join(out_dir, cand)
        if os.path.exists(p):
            src = p
            break
    if src is None:
        raise RuntimeError(
            "Could not find the analysed source video (source.mp4) in "
            f"{out_dir}. Re-run crv with --motion, or pass --assets.")
    return Blueprint(src, data.get("shots", []), data.get("rhythm", {}),
                     data.get("chapters", []), segs)


# --------------------------------------------------------------------------
# Candidate pool — classify short windows of the source (or other) videos
# --------------------------------------------------------------------------

def _classify_clip(video: str, t0: float, t1: float, motion_fps: float) -> dict | None:
    """Trim [t0,t1] to a temp file and classify it as a single shot. Returns a
    normalised candidate dict, or None if it can't be analysed."""
    from . import motion as _motion
    dur = t1 - t0
    if dur <= 0.2:
        return None
    with tempfile.TemporaryDirectory() as td:
        clip = os.path.join(td, "clip.mp4")
        r = _run(["ffmpeg", "-y", "-ss", f"{t0:.3f}", "-i", video,
                  "-t", f"{dur:.3f}", "-c", "copy", clip,
                  "-hide_banner", "-loglevel", "error"])
        if not os.path.exists(clip) or os.path.getsize(clip) == 0:
            return None
        try:
            res = _motion.analyze_motion(clip, td, td, int(dur) or 1,
                                         motion_fps=motion_fps, chapters=False)
        except Exception:
            return None
        shots = res.get("json", {}).get("shots", [])
        if not shots:
            return None
        # take the longest shot in the window as its representative motion
        shot = max(shots, key=lambda s: s["end"] - s["start"])
        return {
            "video": video, "start": t0, "end": t1, "dur": dur,
            "camera": shot["camera"], "motion": shot["motion"],
            "mag": shot.get("mag", 0.0),
        }


def build_candidate_pool(videos: list[str], pool_step: float = 3.0,
                         pool_len: float = 3.0, motion_fps: float = 5.0,
                         max_candidates: int = 400) -> list[dict]:
    """Slide a fixed window over each video and classify every window into a
    candidate segment (camera move + motion level). This pool is what the clone
    planner pulls from to rebuild the viral video's style with fresh content."""
    pool = []
    for video in videos:
        d = _video_duration(video)
        if d <= 0:
            continue
        t = 0.0
        while t + pool_len <= d and len(pool) < max_candidates:
            c = _classify_clip(video, t, min(t + pool_len, d), motion_fps)
            if c:
                pool.append(c)
            t += pool_step
    return pool


def _video_duration(video: str) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", video])
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


# --------------------------------------------------------------------------
# Matching — map each blueprint shot to the best candidate segment
# --------------------------------------------------------------------------

_CAMERA_FAMILY = {
    "pan-left": "pan", "pan-right": "pan",
    "tilt-up": "tilt", "tilt-down": "tilt",
    "zoom-in": "zoom", "zoom-out": "zoom",
    "static": "static", "handheld": "handheld",
}


def _score(cand: dict, target: dict) -> float:
    fam_c = _CAMERA_FAMILY.get(cand["camera"], cand["camera"])
    fam_t = _CAMERA_FAMILY.get(target["camera"], target["camera"])
    cam = 2.0 if fam_c == fam_t else (0.5 if cand["camera"] == target["camera"] else 0.0)
    mag_t = max(0.1, target.get("mag", 1.0))
    mag = -abs(cand["mag"] - target.get("mag", 0.0)) / mag_t
    dur = -abs(cand["dur"] - target["dur"]) / max(0.5, target["dur"])
    return cam + mag + dur


def build_clone_plan(blueprint: Blueprint, candidates: list[dict],
                     llm, topic: str) -> list[dict]:
    """For every blueprint shot, pick the best unused candidate whose motion
    matches, and attach LLM-written on-screen copy."""
    plan = []
    used = set()
    for i, shot in enumerate(blueprint.shots, 1):
        target = {"camera": shot["camera"], "mag": shot.get("mag", 0.0),
                  "dur": shot["end"] - shot["start"]}
        best, best_score = None, -1e9
        for ci, c in enumerate(candidates):
            if ci in used:
                continue
            s = _score(c, target)
            if s > best_score:
                best_score, best = s, c
        if best is None:
            continue
        used.add(candidates.index(best))
        cap = _clone_caption(llm, topic, shot, i)
        plan.append({
            "slot": i, "target_camera": shot["camera"],
            "target_dur": round(target["dur"], 2),
            "src_video": best["video"], "seg_start": best["start"],
            "seg_end": best["end"], "actual_camera": best["camera"],
            "actual_motion": best["motion"], "caption": cap,
        })
    return plan


def _clone_caption(llm, topic: str, shot: dict, slot: int) -> str:
    cam = _CAMERA_WORDS.get(shot["camera"], shot["camera"])
    prompt = (f"ROLE: clone\nTOPIC: {topic}\nCAMERA: {shot['camera']}\n"
              f"Write ONE short on-screen caption (<=12 words) for shot {slot} of a "
              f"short-form video about '{topic}'. The shot uses {cam}. Be punchy, "
              f"no hashtags, no quotes. Return only the caption.")
    try:
        out = llm.complete(prompt, max_tokens=60).strip().strip('"').strip()
        return out or f"Shot {slot}"
    except Exception:
        return f"Shot {slot}"


# --------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------

def _fit_filter(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")


def _emulate_filter(target_camera: str, w: int, h: int, dur: float) -> str | None:
    """A light camera-move emulation applied to an already-fit WxH clip, so a
    matched-but-not-identical segment still reads as the target move. Returns an
    ffmpeg filter string, or None. Assumes its input is already WxH and outputs
    WxH (so aspect is preserved)."""
    fam = _CAMERA_FAMILY.get(target_camera, target_camera)
    d = max(0.5, dur)
    try:
        if fam == "zoom":
            if target_camera == "zoom-in":
                z = f"min(1.0+0.25*on/(30*{d:.1f}),1.3)"
            else:
                z = f"max(1.3-0.25*on/(30*{d:.1f}),1.0)"
            return f"zoompan=z='{z}':d=1:s={w}x{h}:fps=30"
        if fam == "pan":
            if target_camera == "pan-right":
                x = f"(iw*0.15)*(t/{d:.1f})"
            else:
                x = f"(iw*0.15)*(1-t/{d:.1f})"
            return f"crop=iw*0.85:ih:x='{x}':y=0,scale={w}:{h}"
        if fam == "handheld":
            return (f"crop=iw*0.92:ih:x='iw*0.04+20*sin(t*7)':"
                    f"y='ih*0.04+15*cos(t*5)',scale={w}:{h}")
    except Exception:
        return None
    return None


def _render_segment(seg: dict, out_path: str, w: int, h: int) -> bool:
    """Extract one matched segment, retime/pad to the target duration, emulate
    the camera move if needed, and render to a uniform WxH temporary mp4.
    Falls back to a plain fit if the emulation filter fails for any reason."""
    dur = seg["seg_end"] - seg["seg_start"]
    if dur <= 0:
        return False
    target = seg["target_dur"]
    pad = max(0.0, target - dur)
    vpad = f",tpad=stop_mode=add:stop_duration={pad:.2f}" if pad > 0.01 else ""
    apad = f",apad=whole_dur={target:.2f}" if pad > 0.01 else ""

    def _cmd(filt: str) -> list[str]:
        return ["ffmpeg", "-y", "-ss", f"{seg['seg_start']:.3f}", "-i", seg["src_video"],
                "-t", f"{min(dur, target) + 0.05:.3f}",
                "-vf", filt + vpad,
                "-af", "aresample=44100" + apad,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
                out_path, "-hide_banner", "-loglevel", "error"]

    # try with emulation (fit first, then the move on the WxH clip)
    emu = _emulate_filter(seg["target_camera"], w, h, target)
    if emu:
        if _run(_cmd(_fit_filter(w, h) + "," + emu)).returncode == 0 \
                and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True
    # fallback: plain fit + retime
    r = _run(_cmd(_fit_filter(w, h)))
    return os.path.exists(out_path) and os.path.getsize(out_path) > 0


def _caption_card(text: str, w: int, h: int, bg: tuple = (15, 15, 20)) -> str:
    """Render a caption card image (Pillow) and return its path in a temp dir."""
    td = tempfile.gettempdir()
    path = os.path.join(td, f"vs_card_{abs(hash(text))}.png")
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 54)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
        small = font
    # wrap text
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        if len(cur + " " + wd) > 22:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    if cur:
        lines.append(cur)
    lines = lines[:6]
    y = h // 2 - len(lines) * 34
    for ln in lines:
        d.text((w // 2 - d.textlength(ln, font=font) / 2, y), ln, fill=(240, 240, 240), font=font)
        y += 68
    img.save(path)
    return path


def _concat(parts: list[str], out_path: str) -> bool:
    if not parts:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
        lst = f.name
    r = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
              "-c", "copy", out_path, "-hide_banner", "-loglevel", "error"])
    os.unlink(lst)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 0


# --------------------------------------------------------------------------
# Mode: clone
# --------------------------------------------------------------------------

def render_clone(blueprint: Blueprint, candidates: list[dict], out_path: str,
                 llm, topic: str, w: int = 1080, h: int = 1920) -> dict:
    plan = build_clone_plan(blueprint, candidates, llm, topic)
    if not plan:
        raise RuntimeError("No matching segments found in the candidate pool.")
    td = tempfile.mkdtemp(prefix="vs_clone_")
    parts = []
    for seg in plan:
        sp = os.path.join(td, f"seg_{seg['slot']:02d}.mp4")
        if _render_segment(seg, sp, w, h):
            parts.append(sp)
    ok = _concat(parts, out_path)
    # optional 2s title card at the very start
    if ok:
        card = _caption_card(f"{topic}\n(viral-style remix)", w, h)
        cp = os.path.join(td, "title.mp4")
        _run(["ffmpeg", "-y", "-loop", "1", "-i", card, "-t", "2",
              "-vf", _fit_filter(w, h), "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-r", "30", cp, "-hide_banner", "-loglevel", "error"])
        if os.path.exists(cp):
            final = out_path + ".tmp.mp4"
            if _concat([cp, out_path], final):
                shutil.move(final, out_path)
    shutil.rmtree(td, ignore_errors=True)
    # also persist the plan for the user / downstream tools
    plan_path = out_path + ".plan.json"
    json.dump({"topic": topic, "plan": plan}, open(plan_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return {"out": out_path, "plan": plan, "plan_path": plan_path,
            "segments": len(plan)}


# --------------------------------------------------------------------------
# Mode: breakdown
# --------------------------------------------------------------------------

def _narration(llm, topic: str, shot: dict, slot: int, transcript_segs: list[dict]) -> str:
    cam = _CAMERA_WORDS.get(shot["camera"], shot["camera"])
    spoken = ""
    for s in transcript_segs:
        if s["start"] <= shot["start"] < s["end"]:
            spoken = s["text"]
            break
    prompt = (f"ROLE: breakdown\nTOPIC: {topic}\nCAMERA: {shot['camera']}\n"
              f"Write ONE sentence (<=25 words) explaining why this {cam} shot works "
              f"in a short about '{topic}'. Reference the camera move, not the words. "
              f"No hashtags. Return only the sentence.")
    try:
        return llm.complete(prompt, max_tokens=80).strip().strip('"').strip() or cam
    except Exception:
        return f"This {cam} keeps the viewer anchored through the beat."


def render_breakdown(blueprint: Blueprint, out_path: str, llm, topic: str,
                     w: int = 1080, h: int = 1920, tts: bool = False) -> dict:
    td = tempfile.mkdtemp(prefix="vs_bd_")
    parts = []
    plan = []
    for i, shot in enumerate(blueprint.shots, 1):
        # representative frame halfway through the shot
        mid = (shot["start"] + shot["end"]) / 2
        fr = os.path.join(td, f"f_{i:02d}.jpg")
        _run(["ffmpeg", "-y", "-ss", f"{mid:.3f}", "-i", blueprint.source_video,
              "-frames:v", "1", "-vf", f"scale={w}:-1", fr,
              "-hide_banner", "-loglevel", "error"])
        narr = _narration(llm, topic, shot, i, blueprint.transcript)
        # card: shot # + camera + narration
        card_text = f"#{i:02d}  {shot['camera']}  ({shot['motion']})\n{narr}"
        card = _caption_card(card_text, w, h)
        # frame clip (3s hold) + 3s narration card
        fclip = os.path.join(td, f"fc_{i:02d}.mp4")
        _run(["ffmpeg", "-y", "-loop", "1", "-i", fr, "-t", "3",
              "-vf", _fit_filter(w, h), "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-r", "30", fclip, "-hide_banner", "-loglevel", "error"])
        cclip = os.path.join(td, f"cc_{i:02d}.mp4")
        _run(["ffmpeg", "-y", "-loop", "1", "-i", card, "-t", "3",
              "-vf", _fit_filter(w, h), "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-r", "30", cclip, "-hide_banner", "-loglevel", "error"])
        if os.path.exists(fclip):
            parts.append(fclip)
        if os.path.exists(cclip):
            parts.append(cclip)
        plan.append({"slot": i, "camera": shot["camera"], "motion": shot["motion"],
                     "narration": narr})
        if tts:
            _tts(narr, os.path.join(td, f"a_{i:02d}.m4a"))
    ok = _concat(parts, out_path)
    plan_path = out_path + ".plan.json"
    json.dump({"topic": topic, "mode": "breakdown", "plan": plan},
              open(plan_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    shutil.rmtree(td, ignore_errors=True)
    return {"out": out_path, "plan": plan, "plan_path": plan_path,
            "segments": len(plan)}


def _tts(text: str, out_path: str) -> bool:
    """Best-effort TTS: macOS `say` (AAC) if present, else espeak, else skip."""
    if shutil.which("say"):
        r = _run(["say", "-o", out_path, "-f", "aac", text])
        return os.path.exists(out_path)
    if shutil.which("espeak"):
        r = _run(["espeak", "-w", out_path, text])
        return os.path.exists(out_path)
    return False
