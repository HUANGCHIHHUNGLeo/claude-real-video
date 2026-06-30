"""Core pipeline: fetch a video (URL or file), extract scene-aware + deduplicated
frames, optionally transcribe audio, and write a manifest an LLM can read."""
from __future__ import annotations
import glob
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


@dataclass
class Result:
    out_dir: str
    video: str
    duration: int
    frames_dir: str
    frame_count: int
    scene_frames: int
    transcript_path: str | None
    manifest_path: str
    transcript_note: str = ""


def fetch_video(src: str, out_dir: str, cookies: str | None = None) -> str:
    """Download via yt-dlp (URL) or copy a local file. cookies is an optional
    Netscape-format cookie file for sites that require login (your own,
    authorised use only)."""
    dest = os.path.join(out_dir, "source.mp4")
    if src.startswith(("http://", "https://")):
        if not _have("yt-dlp"):
            raise RuntimeError("yt-dlp not found. Install it: pip install yt-dlp")
        base = ["yt-dlp", src, "-o", dest, "--merge-output-format", "mp4", "--no-warnings", "-q"]
        _run(base)
        if not os.path.exists(dest) and cookies:
            _run(base + ["--cookies", cookies])
        if not os.path.exists(dest):
            # yt-dlp may have written a different extension
            hits = sorted(glob.glob(os.path.join(out_dir, "source.*")))
            if hits:
                dest = hits[0]
        if not os.path.exists(dest):
            raise RuntimeError("Download failed (private video? try --cookies your_cookies.txt)")
    else:
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        shutil.copy(src, dest)
    return dest


def _duration(video: str) -> int:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", video])
    try:
        return int(float(r.stdout.strip()))
    except (ValueError, AttributeError):
        return 0


def _has_audio(video: str) -> bool:
    """True if the file carries at least one audio stream."""
    r = _run(["ffprobe", "-v", "error", "-select_streams", "a",
              "-show_entries", "stream=codec_type", "-of", "csv=p=0", video])
    return bool(r.stdout.strip())


def extract_frames(video: str, frames_dir: str, scene: float, fps_floor: float,
                   max_frames: int) -> tuple[int, int]:
    """Scene-change frames (every visual change) + a density floor (so dynamic
    videos are never under-sampled). Returns (scene_count, total_before_dedup)."""
    os.makedirs(frames_dir, exist_ok=True)
    _run(["ffmpeg", "-i", video, "-vf", f"select='gt(scene,{scene})',scale=640:-1",
          "-vsync", "vfr", os.path.join(frames_dir, "scene_%03d.jpg"),
          "-hide_banner", "-loglevel", "error"])
    scene_n = len(glob.glob(os.path.join(frames_dir, "scene_*.jpg")))
    _run(["ffmpeg", "-i", video, "-vf", f"fps=1/{fps_floor},scale=640:-1",
          os.path.join(frames_dir, "floor_%03d.jpg"),
          "-hide_banner", "-loglevel", "error"])
    total = len(glob.glob(os.path.join(frames_dir, "*.jpg")))
    if total > max_frames:
        floors = sorted(glob.glob(os.path.join(frames_dir, "floor_*.jpg")))
        for i, f in enumerate(floors):
            if i % 3 != 0:
                os.remove(f)
    return scene_n, len(glob.glob(os.path.join(frames_dir, "*.jpg")))


def dedup_frames(frames_dir: str, threshold: int = 8) -> int:
    """Drop near-identical consecutive frames via average-hash. This is the key
    win over fixed-budget extractors: a static slide collapses to one frame."""
    try:
        from PIL import Image
    except ImportError:
        return len(glob.glob(os.path.join(frames_dir, "*.jpg")))

    def ahash(path: str, size: int = 12) -> list[int]:
        im = Image.open(path).convert("L").resize((size, size))
        px = list(im.getdata())
        avg = sum(px) / len(px)
        return [1 if v > avg else 0 for v in px]

    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    kept: list[str] = []
    last: list[int] | None = None
    for f in frames:
        h = ahash(f)
        if last is None or sum(a != b for a, b in zip(h, last)) > threshold:
            kept.append(f)
            last = h
        else:
            os.remove(f)
    for i, f in enumerate(sorted(kept), 1):
        os.rename(f, os.path.join(frames_dir, f"tmp_{i:03d}.jpg"))
    for f in sorted(os.listdir(frames_dir)):
        if f.startswith("tmp_"):
            os.rename(os.path.join(frames_dir, f), os.path.join(frames_dir, "frame_" + f[4:]))
    return len(kept)


def _has_subtitle_stream(video: str) -> bool:
    r = _run(["ffprobe", "-v", "error", "-select_streams", "s",
              "-show_entries", "stream=index", "-of", "csv=p=0", video])
    return bool(r.stdout.strip())


def _subs_to_text(sub_path: str, out_txt: str) -> str | None:
    """Convert an .srt/.vtt subtitle file to plain text (drop indices,
    timecodes and styling tags). Returns out_txt on success."""
    try:
        raw = open(sub_path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return None
    lines: list[str] = []
    for ln in raw.splitlines():
        s = ln.strip().lstrip("﻿").strip()  # drop BOM if present
        if not s or s.startswith("WEBVTT") or s.isdigit() or "-->" in s:
            continue
        s = re.sub(r"<[^>]+>", "", s)  # strip vtt inline tags like <v ->
        if s:
            lines.append(s)
    text = "\n".join(lines).strip()
    if not text:
        return None
    open(out_txt, "w", encoding="utf-8").write(text + "\n")
    return out_txt


def existing_subtitles(src: str, video: str, out_dir: str) -> str | None:
    """Use subtitles the video already ships with, instead of re-transcribing.
    Checks (1) a sidecar .srt/.vtt next to a local source file, then
    (2) an embedded subtitle stream. Returns the transcript path, or None.
    This is faster and more accurate than Whisper when captions already exist."""
    dst = os.path.join(out_dir, "transcript.txt")
    # 1) sidecar file next to the original source (local files only)
    if not src.startswith(("http://", "https://")):
        base = os.path.splitext(src)[0]
        for ext in (".srt", ".vtt"):
            cand = base + ext
            if os.path.exists(cand) and _subs_to_text(cand, dst):
                return dst
    # 2) embedded subtitle stream
    if _has_subtitle_stream(video):
        raw = os.path.join(out_dir, "_embedded.srt")
        _run(["ffmpeg", "-y", "-i", video, "-map", "0:s:0", raw,
              "-hide_banner", "-loglevel", "error"])
        if os.path.exists(raw):
            ok = _subs_to_text(raw, dst)
            try:
                os.remove(raw)
            except OSError:
                pass
            if ok:
                return dst
    return None


def transcribe(video: str, out_dir: str, lang: str | None) -> str | None:
    """Optional: extract audio + run Whisper if the `whisper` CLI is installed."""
    if not _have("whisper"):
        return None
    wav = os.path.join(out_dir, "audio.wav")
    _run(["ffmpeg", "-i", video, "-vn", "-ar", "16000", "-ac", "1", wav,
          "-hide_banner", "-loglevel", "error"])
    if not os.path.exists(wav):
        return None
    cmd = ["whisper", wav, "--model", "base", "--output_format", "txt", "--output_dir", out_dir]
    if lang and lang != "auto":
        cmd += ["--language", lang]
    _run(cmd)
    src = os.path.join(out_dir, "audio.txt")
    dst = os.path.join(out_dir, "transcript.txt")
    if os.path.exists(src):
        os.replace(src, dst)
        return dst
    return None


def process(src: str, out_dir: str, *, scene: float = 0.30, fps_floor: float = 1.0,
            max_frames: int = 150, lang: str | None = "auto", cookies: str | None = None,
            do_transcribe: bool = True, dedup_threshold: int = 8) -> Result:
    os.makedirs(out_dir, exist_ok=True)
    frames_dir = os.path.join(out_dir, "frames")
    video = fetch_video(src, out_dir, cookies=cookies)
    dur = _duration(video)
    scene_n, _ = extract_frames(video, frames_dir, scene, fps_floor, max_frames)
    kept = dedup_frames(frames_dir, dedup_threshold)

    # Text for the LLM: prefer subtitles the video already has (faster + more
    # accurate); only fall back to Whisper when there are none. Be honest about
    # *why* there's no transcript — a silent video is not a missing whisper install.
    transcript = None
    if not do_transcribe:
        note = "(skipped: --no-transcribe)"
    elif (transcript := existing_subtitles(src, video, out_dir)):
        note = f"{transcript} (from the video's own subtitles)"
    elif not _have("whisper"):
        note = "(none — no existing subtitles; install whisper to transcribe: pip install openai-whisper)"
    elif not _has_audio(video):
        note = "(none — this video has no subtitles and no audio track)"
    else:
        transcript = transcribe(video, out_dir, lang)
        note = f"{transcript} (transcribed by whisper)" if transcript else "(none — transcription failed)"

    manifest = os.path.join(out_dir, "MANIFEST.txt")
    lines = [
        f"source: {src}",
        f"duration: {dur}s | frames: {kept} (scene {scene_n} + density floor, deduped)",
        f"frames dir: {frames_dir}",
        f"transcript: {note}",
        "--- transcript ---",
    ]
    if transcript and os.path.exists(transcript):
        lines.append(open(transcript, encoding="utf-8").read().strip())
    open(manifest, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    return Result(out_dir=out_dir, video=video, duration=dur, frames_dir=frames_dir,
                  frame_count=kept, scene_frames=scene_n,
                  transcript_path=transcript, manifest_path=manifest,
                  transcript_note=note)
