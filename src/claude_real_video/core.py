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
    extracted_frames: int
    transcript_path: str | None
    manifest_path: str
    transcript_note: str = ""
    audio_path: str | None = None
    report_path: str | None = None


def fetch_video(src: str, out_dir: str, cookies: str | None = None, cookies_from_browser: str | None = None) -> str:
    """Download via yt-dlp (URL) or copy a local file. cookies is an optional
    Netscape-format cookie file for sites that require login (your own,
    authorised use only)."""
    dest = os.path.join(out_dir, "source.mp4")
    if src.startswith(("http://", "https://")):
        if not _have("yt-dlp"):
            raise RuntimeError("yt-dlp not found. Install it: pip install yt-dlp")
        base = ["yt-dlp", src, "-o", dest, "--merge-output-format", "mp4", "--no-warnings", "-q"]
        _run(base)
        if not os.path.exists(dest) and cookies_from_browser:
            _run(base + ["--cookies-from-browser", cookies_from_browser])
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


def _fps(video: str) -> float:
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", video])
    try:
        num, den = r.stdout.strip().split("/")
        return float(num) / float(den) if float(den) else 25.0
    except (ValueError, ZeroDivisionError, AttributeError):
        return 25.0


def extract_frames(video: str, frames_dir: str, scene: float, fps_floor: float,
                   anchors: list[int] | None = None) -> int:
    """One chronological pass: every scene change OR one frame per `fps_floor`
    seconds, whichever comes first. A single select filter keeps the frames in
    time order, so dedup compares true neighbours (two passes used to interleave
    scene_/floor_ files out of order). `anchors` are extra frame numbers forced
    into the same pass (text-anchored extraction, issue #5) so ordering — and
    therefore dedup — still holds. Returns the extracted count."""
    os.makedirs(frames_dir, exist_ok=True)
    every_n = max(1, round(_fps(video) * fps_floor))
    sel = f"gt(scene,{scene})+not(mod(n,{every_n}))"
    if anchors:
        sel += "+" + "+".join(f"eq(n,{n})" for n in anchors)
    _run(["ffmpeg", "-i", video,
          "-vf", f"select='{sel}',scale=640:-1",
          "-vsync", "vfr", os.path.join(frames_dir, "raw_%05d.jpg"),
          "-hide_banner", "-loglevel", "error"])
    return len(glob.glob(os.path.join(frames_dir, "raw_*.jpg")))


def _scene_scores(video: str) -> list[tuple[int, float]]:
    """One metadata pass: per-frame scene-change score from ffmpeg's scene
    detector, without extracting anything. Returns [(frame_no, score), ...]."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        meta = tf.name
    try:
        _run(["ffmpeg", "-i", video,
              "-vf", f"select='gte(scene,0)',metadata=print:file={meta}",
              "-f", "null", "-", "-hide_banner", "-loglevel", "error"])
        scores, frame_no = [], None
        for line in open(meta, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith("frame:"):
                try:
                    frame_no = int(line.split("frame:")[1].split()[0])
                except (ValueError, IndexError):
                    frame_no = None
            elif "lavfi.scene_score=" in line and frame_no is not None:
                try:
                    scores.append((frame_no, float(line.split("=")[1])))
                except ValueError:
                    pass
        return scores
    finally:
        os.unlink(meta)


def extract_frames_adaptive(video: str, frames_dir: str, fps_floor: float,
                            window_s: float = 2.0, mult: float = 3.0,
                            min_content: float = 0.04,
                            anchors: list[int] | None = None) -> int:
    """Adaptive extraction for slow-changing content (issue #2): a frame is a
    keyframe when its scene score exceeds `mult` x the rolling average of the
    previous `window_s` seconds AND an absolute floor `min_content` — so gradual
    morphs (squash/stretch, slow pans) that never cross a fixed threshold still
    register against their own quiet neighbourhood. The fps_floor safety net
    still guarantees a frame per interval. Falls back to plain extraction when
    the score pass yields nothing (e.g. single-frame or still videos)."""
    scores = _scene_scores(video)
    if not scores:
        return extract_frames(video, frames_dir, 0.30, fps_floor, anchors=anchors)
    fps = _fps(video)
    win = max(1, round(fps * window_s))
    every_n = max(1, round(fps * fps_floor))
    picked, rolling = [], []
    last_floor = -every_n
    for i, (n, s) in enumerate(scores):
        avg = (sum(rolling) / len(rolling)) if rolling else 0.0
        if (s >= min_content and s >= avg * mult) or (n - last_floor >= every_n):
            picked.append(n)
            if n - last_floor >= every_n:
                last_floor = n
        rolling.append(s)
        if len(rolling) > win:
            rolling.pop(0)
    if not picked:
        return extract_frames(video, frames_dir, 0.30, fps_floor, anchors=anchors)
    if anchors:
        picked = sorted(set(picked) | set(anchors))
    os.makedirs(frames_dir, exist_ok=True)
    expr = "+".join(f"eq(n,{n})" for n in picked)
    _run(["ffmpeg", "-i", video,
          "-vf", f"select='{expr}',scale=640:-1",
          "-vsync", "vfr", os.path.join(frames_dir, "raw_%05d.jpg"),
          "-hide_banner", "-loglevel", "error"])
    return len(glob.glob(os.path.join(frames_dir, "raw_*.jpg")))


def dedup_frames(frames_dir: str, threshold: float = 8, window: int = 4,
                 max_frames: int = 150,
                 dropped_dir: str | None = None) -> tuple[int, list[dict]]:
    """Drop near-duplicate frames by real pixel difference (downscaled grayscale,
    like videostil's pixelmatch approach — more faithful than a perceptual hash,
    which goes blind on flat colours and brightness-only changes) against a
    sliding window of the last `window` kept frames. The window also catches
    A-B-A alternation — a shot the model has already seen doesn't come back
    just because a different frame sat in between. `threshold` is the percent
    of pixels that must change for a frame to count as new.
    Returns (kept_count, per-frame records for the optional report)."""
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    try:
        from PIL import Image
    except ImportError:
        return len(frames), []

    def sig(path: str, size: int = 16) -> list[tuple[int, int, int]]:
        # RGB, not grayscale: hues with equal luma (a red→green cut) must not
        # look identical to the comparator
        return list(Image.open(path).convert("RGB").resize((size, size)).getdata())

    def pct_diff(a: list, b: list, tol: int = 25) -> float:
        changed = sum(max(abs(x[0] - y[0]), abs(x[1] - y[1]), abs(x[2] - y[2])) > tol
                      for x, y in zip(a, b))
        return 100.0 * changed / len(a)

    kept: list[str] = []
    recent: list[list[int]] = []  # signatures of the last `window` kept frames
    records: list[dict] = []
    for f in frames:
        h = sig(f)
        dist = min((pct_diff(h, k) for k in recent), default=None)
        if dist is None or dist > threshold:
            kept.append(f)
            recent.append(h)
            if len(recent) > window:
                recent.pop(0)
            records.append({"name": os.path.basename(f), "dist": dist, "kept": True})
        else:
            if dropped_dir:
                os.makedirs(dropped_dir, exist_ok=True)
                shutil.move(f, os.path.join(dropped_dir, os.path.basename(f)))
            else:
                os.remove(f)
            records.append({"name": os.path.basename(f), "dist": dist, "kept": False})

    # cap: thin uniformly *after* dedup so the survivors stay spread across the video
    if len(kept) > max_frames:
        step = len(kept) / max_frames
        keep_idx = {int(i * step) for i in range(max_frames)}
        for i, f in enumerate(list(kept)):
            if i not in keep_idx:
                kept.remove(f)
                os.remove(f)
                for rec in records:
                    if rec["name"] == os.path.basename(f):
                        rec["kept"] = False
                        rec["capped"] = True

    renames = {}
    for i, f in enumerate(sorted(kept), 1):
        renames[os.path.basename(f)] = f"frame_{i:03d}.jpg"
        os.rename(f, os.path.join(frames_dir, f"tmp_{i:03d}.jpg"))
    for f in sorted(os.listdir(frames_dir)):
        if f.startswith("tmp_"):
            os.rename(os.path.join(frames_dir, f), os.path.join(frames_dir, "frame_" + f[4:]))
    for rec in records:
        if rec["kept"]:
            rec["name"] = renames.get(rec["name"], rec["name"])
    return len(kept), records


def write_report(out_dir: str, records: list[dict], threshold: float, window: int) -> str:
    """Self-contained report.html showing every extracted frame — kept or
    dropped — with its hash distance, so you can eyeball whether the threshold
    is too tight or too loose (videostil's Analysis Viewer, minus the server)."""
    kept_n = sum(1 for r in records if r["kept"])
    rows = []
    for r in records:
        src = f"frames/{r['name']}" if r["kept"] else f"dropped/{r['name']}"
        why = "capped" if r.get("capped") else ("kept" if r["kept"] else "dropped")
        dist = "first" if r["dist"] is None else f"{r['dist']:.1f}%"
        rows.append(
            f'<figure class="{why}"><img src="{src}" loading="lazy">'
            f'<figcaption>{r["name"]}<br>dist {dist} · {why}</figcaption></figure>')
    html = f"""<!doctype html><meta charset="utf-8"><title>crv dedup report</title>
<style>
body{{font:14px system-ui;margin:20px;background:#111;color:#ddd}}
.grid{{display:flex;flex-wrap:wrap;gap:10px}}
figure{{margin:0;width:200px}}img{{width:100%;border-radius:4px}}
figcaption{{font-size:11px;color:#999;padding:2px 0}}
.dropped img{{opacity:.35;outline:2px solid #a33}}
.capped img{{opacity:.35;outline:2px solid #a80}}
.kept img{{outline:2px solid #3a6}}
</style>
<h2>crv dedup report</h2>
<p>threshold {threshold} · window {window} · kept {kept_n} / {len(records)}
(green kept · red duplicate · orange removed by --max-frames cap)</p>
<div class="grid">{''.join(rows)}</div>
"""
    path = os.path.join(out_dir, "report.html")
    open(path, "w", encoding="utf-8").write(html)
    return path


def _has_subtitle_stream(video: str) -> bool:
    r = _run(["ffprobe", "-v", "error", "-select_streams", "s",
              "-show_entries", "stream=index", "-of", "csv=p=0", video])
    return bool(r.stdout.strip())



def _parse_cues(raw: str) -> list[dict]:
    """Parse srt/vtt subtitle text into timestamped segments
    [{start, end, text}] — written next to transcript.txt as transcript.json."""
    segs: list[dict] = []
    tre = re.compile(
        r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*"
        r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})")
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip()):
        lines = [l for l in block.split("\n")
                 if l.strip() and not l.strip().startswith("WEBVTT")]
        ti = mm = None
        for i, l in enumerate(lines):
            mm = tre.search(l)
            if mm:
                ti = i
                break
        if ti is None:
            continue
        g = [int(x) if x else 0 for x in mm.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        text = " ".join(re.sub(r"<[^>]+>", "", t).strip() for t in lines[ti + 1:]).strip()
        if text:
            segs.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return segs


def _segments_from_whisper_json(path: str) -> list[dict]:
    """Extract [{start, end, text}] from whisper's json output."""
    try:
        import json as _json
        data = _json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    segs = []
    for s in data.get("segments", []):
        txt = str(s.get("text", "")).strip()
        if txt:
            segs.append({"start": round(float(s.get("start", 0)), 2),
                         "end": round(float(s.get("end", 0)), 2), "text": txt})
    return segs


def _write_transcript_json(out_dir: str, segments: list[dict]) -> str | None:
    """Persist timestamped transcript segments next to transcript.txt so
    downstream tools (and your LLM) get timings, not just words."""
    if not segments:
        return None
    import json as _json
    p = os.path.join(out_dir, "transcript.json")
    with open(p, "w", encoding="utf-8") as f:
        _json.dump({"segments": segments}, f, ensure_ascii=False, indent=1)
    return p


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
                try:
                    _write_transcript_json(out_dir, _parse_cues(
                        open(cand, encoding="utf-8", errors="ignore").read()))
                except OSError:
                    pass
                return dst
    # 2) embedded subtitle stream
    if _has_subtitle_stream(video):
        raw = os.path.join(out_dir, "_embedded.srt")
        _run(["ffmpeg", "-y", "-i", video, "-map", "0:s:0", raw,
              "-hide_banner", "-loglevel", "error"])
        if os.path.exists(raw):
            ok = _subs_to_text(raw, dst)
            if ok:
                try:
                    _write_transcript_json(out_dir, _parse_cues(
                        open(raw, encoding="utf-8", errors="ignore").read()))
                except OSError:
                    pass
            try:
                os.remove(raw)
            except OSError:
                pass
            if ok:
                return dst
    return None


def _subtitle_cue_times(src: str, video: str, out_dir: str) -> list[float]:
    """Start time (seconds) of every subtitle cue — from a sidecar .srt/.vtt
    next to a local source first, else the embedded subtitle stream (same
    lookup order as existing_subtitles). Empty list when the video ships no
    captions; OCR of burned-in text is deliberately out of scope (issue #5
    is subtitle-timestamp-driven only, phase 1)."""
    sub_path, cleanup = None, False
    if not src.startswith(("http://", "https://")):
        base = os.path.splitext(src)[0]
        for ext in (".srt", ".vtt"):
            if os.path.exists(base + ext):
                sub_path = base + ext
                break
    if sub_path is None and _has_subtitle_stream(video):
        sub_path = os.path.join(out_dir, "_cues.srt")
        _run(["ffmpeg", "-y", "-i", video, "-map", "0:s:0", sub_path,
              "-hide_banner", "-loglevel", "error"])
        cleanup = True
        if not os.path.exists(sub_path):
            return []
    if sub_path is None:
        return []
    try:
        raw = open(sub_path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return []
    finally:
        if cleanup:
            try:
                os.remove(sub_path)
            except OSError:
                pass
    # srt uses HH:MM:SS,mmm; vtt uses [HH:]MM:SS.mmm — hours optional
    times = []
    for m in re.finditer(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->", raw):
        h, mnt, s, ms = (int(g) if g else 0 for g in m.groups())
        times.append(h * 3600 + mnt * 60 + s + ms / 1000.0)
    return sorted(times)


def _text_anchor_frames(times: list[float], fps: float, min_gap: float = 1.0) -> list[int]:
    """Cue start times → frame numbers to force, at most one per `min_gap`
    seconds so dense captions (karaoke-style, rapid dialogue) don't flood the
    extraction — dedup would drop the extras anyway, but they'd still cost an
    extraction pass each."""
    picked, last = [], -min_gap
    for t in times:
        if t - last >= min_gap:
            picked.append(round(t * fps))
            last = t
    return picked


def extract_full_audio(video: str, out_dir: str) -> str | None:
    """Save the complete original soundtrack (music + speech + effects) so an
    audio-capable model can actually *hear* the video — not just read the words.
    Copies the stream losslessly when the codec allows, else re-encodes to AAC."""
    if not _has_audio(video):
        return None
    dst = os.path.join(out_dir, "audio.m4a")
    # try a lossless stream copy first (works for AAC/ALAC sources)
    _run(["ffmpeg", "-y", "-i", video, "-vn", "-c:a", "copy", dst,
          "-hide_banner", "-loglevel", "error"])
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    # fallback: re-encode (e.g. opus/vorbis sources) at a high bitrate
    _run(["ffmpeg", "-y", "-i", video, "-vn", "-c:a", "aac", "-b:a", "192k", dst,
          "-hide_banner", "-loglevel", "error"])
    return dst if os.path.exists(dst) and os.path.getsize(dst) > 0 else None


def transcribe(video: str, out_dir: str, lang: str | None, model: str = "base") -> str | None:
    """Optional: extract audio + run Whisper if the `whisper` CLI is installed."""
    if not _have("whisper"):
        return None
    wav = os.path.join(out_dir, "audio.wav")
    _run(["ffmpeg", "-i", video, "-vn", "-ar", "16000", "-ac", "1", wav,
          "-hide_banner", "-loglevel", "error"])
    if not os.path.exists(wav):
        return None
    # json carries per-segment timestamps (saved as transcript.json); txt stays
    # the plain fallback. "all" writes both plus srt/vtt/tsv we clean up.
    cmd = ["whisper", wav, "--model", model, "--output_format", "all", "--output_dir", out_dir]
    if lang and lang != "auto":
        cmd += ["--language", lang]
    _run(cmd)
    jsrc = os.path.join(out_dir, "audio.json")
    if os.path.exists(jsrc):
        _write_transcript_json(out_dir, _segments_from_whisper_json(jsrc))
    for ext in ("json", "srt", "vtt", "tsv"):  # tidy whisper's extra outputs
        try:
            os.remove(os.path.join(out_dir, f"audio.{ext}"))
        except OSError:
            pass
    src = os.path.join(out_dir, "audio.txt")
    dst = os.path.join(out_dir, "transcript.txt")
    if os.path.exists(src):
        os.replace(src, dst)
        return dst
    return None


def make_grids(frames_dir: str, out_dir: str, cols: int = 3, rows: int = 3,
               cell_width: int = 480) -> list[str]:
    """Tile the kept frames, in order, into contact-sheet grids. A model reading
    consecutive frames side by side in one image follows motion and progression
    far better than the same frames seen one at a time."""
    from PIL import Image, ImageDraw
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    if not frames:
        return []
    grids_dir = os.path.join(out_dir, "grids")
    os.makedirs(grids_dir, exist_ok=True)
    per = cols * rows
    sheets = []
    label_h = 22
    for gi in range(0, len(frames), per):
        batch = frames[gi:gi + per]
        first = Image.open(batch[0])
        cw = cell_width
        ch = int(first.height * cw / first.width) + label_h
        sheet = Image.new("RGB", (cols * cw, rows * ch), "black")
        draw = ImageDraw.Draw(sheet)
        for i, f in enumerate(batch):
            im = Image.open(f)
            im = im.resize((cw, ch - label_h))
            x, y = (i % cols) * cw, (i // cols) * ch
            sheet.paste(im, (x, y + label_h))
            draw.text((x + 6, y + 4), os.path.basename(f), fill="white")
        dest = os.path.join(grids_dir, f"grid_{gi // per + 1:02d}.jpg")
        sheet.save(dest, quality=85)
        sheets.append(dest)
    return sheets


def save_to_kb(kb_dir: str, manifest_path: str, src: str) -> str:
    """Copy the analysis into a knowledge-base folder as a dated markdown note,
    so it lives next to the user's other notes instead of dying in ./crv-out."""
    import datetime, re as _re
    os.makedirs(kb_dir, exist_ok=True)
    slug = _re.sub(r"[^A-Za-z0-9一-鿿]+", "-", os.path.basename(src.rstrip("/")))[:60].strip("-") or "video"
    dest = os.path.join(kb_dir, f"{datetime.date.today().isoformat()}-{slug}.md")
    body = open(manifest_path, encoding="utf-8").read()
    open(dest, "w", encoding="utf-8").write(f"# Video analysis — {src}\n\n```\n{body}\n```\n")
    return dest


def process(src: str, out_dir: str, *, scene: float = 0.30, fps_floor: float = 1.0,
            adaptive: bool = False, text_anchors: bool = False,
            max_frames: int = 150, lang: str | None = "auto", cookies: str | None = None,
            do_transcribe: bool = True, dedup_threshold: float = 8, dedup_window: int = 4,
            keep_audio: bool = False, report: bool = False, why: str | None = None, whisper_model: str = "base", cookies_from_browser: str | None = None) -> Result:
    os.makedirs(out_dir, exist_ok=True)
    frames_dir = os.path.join(out_dir, "frames")
    video = fetch_video(src, out_dir, cookies=cookies, cookies_from_browser=cookies_from_browser)
    dur = _duration(video)
    anchors = (_text_anchor_frames(_subtitle_cue_times(src, video, out_dir), _fps(video))
               if text_anchors else None)
    extracted = (extract_frames_adaptive(video, frames_dir, fps_floor, anchors=anchors)
                 if adaptive else extract_frames(video, frames_dir, scene, fps_floor, anchors=anchors))
    kept, records = dedup_frames(frames_dir, dedup_threshold, dedup_window, max_frames,
                                 dropped_dir=os.path.join(out_dir, "dropped") if report else None)
    report_path = write_report(out_dir, records, dedup_threshold, dedup_window) if report else None

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
        transcript = transcribe(video, out_dir, lang, model=whisper_model)
        note = f"{transcript} (transcribed by whisper)" if transcript else "(none — transcription failed)"

    # Optionally keep the full original soundtrack (music + speech + effects) for
    # models that can listen to audio directly — the transcript only has the words.
    audio_path = extract_full_audio(video, out_dir) if keep_audio else None

    manifest = os.path.join(out_dir, "MANIFEST.txt")
    lines = []
    if why:
        # The reader's job, stated up front: focus the analysis instead of a
        # wandering summary. This line is for the LLM that reads this manifest.
        lines += [f"viewing intent: {why}",
                  "(reader: analyse the frames and transcript with this intent as the lens — "
                  "surface what serves it first, skip what doesn't)", ""]
    lines += [
        f"source: {src}",
        f"duration: {dur}s | frames: {kept} (scene-change + density floor"
        + (f" + {len(anchors)} text anchors" if anchors else "")
        + f", deduped from {extracted} extracted)",
        f"frames dir: {frames_dir}",
        f"transcript: {note}",
    ]
    if keep_audio:
        lines.append(f"audio: {audio_path or '(none — this video has no audio track)'}")
    lines.append("--- transcript ---")
    if transcript and os.path.exists(transcript):
        lines.append(open(transcript, encoding="utf-8").read().strip())
    open(manifest, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    return Result(out_dir=out_dir, video=video, duration=dur, frames_dir=frames_dir,
                  frame_count=kept, extracted_frames=extracted,
                  transcript_path=transcript, manifest_path=manifest,
                  transcript_note=note, audio_path=audio_path, report_path=report_path)
