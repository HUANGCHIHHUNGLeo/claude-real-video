"""--motion: tell an LLM *how* a video moves, not just what's on screen.

Everything here runs locally with ffmpeg + OpenCV — no ML models to download,
no cloud uploads. Given a video it produces, in plain text for the manifest:

  - camera-move classification per shot (static / pan / tilt / zoom / handheld)
  - editing rhythm (shot count, cuts/min, duration stats, cuts by thirds)
  - action bursts: high-motion shots get extra 0.2s-apart frame sequences so a
    model reads movement as a progression instead of guessing between keyframes

The heavy lifting samples a low-resolution frame grid (default 5 fps), estimates
a global affine motion per frame pair (Shi-Tomasi + Lucas-Kanade + partial
affine), then classifies each shot from the accumulated translation, scale drift
and motion-direction consistency.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover — surfaced as a clean error by callers
    cv2 = None


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV is required for --motion. Install it: "
            "pip install \"claude-real-video[motion]\"  (or pip install opencv-python-headless numpy)")


# --- per-frame motion estimation ------------------------------------------------

def _load_gray(path: str, w: int = 160) -> np.ndarray | None:
    im = cv2.imread(path)
    if im is None:
        return None
    h = max(1, int(round(im.shape[0] * w / im.shape[1])))
    im = cv2.resize(im, (w, h))
    return cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)


def _global_motion(prev: np.ndarray, cur: np.ndarray) -> dict | None:
    """Estimate the dominant camera transform between two frames.

    Returns the partial affine decomposition: translation (tx, ty) in pixels of
    the *downscaled* frame, scale (1 == none), rotation in degrees, mean optical
    flow magnitude (pixels), and the inlier ratio (how well a single global
    transform explains the motion). None when too few features track.
    """
    p0 = cv2.goodFeaturesToTrack(
        prev, maxCorners=200, qualityLevel=0.01, minDistance=8, blockSize=7)
    if p0 is None or len(p0) < 8:
        return None
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None)
    if p1 is None:
        return None
    good0 = p0[st == 1]
    good1 = p1[st == 1]
    if len(good0) < 8:
        return None
    M, inliers = cv2.estimateAffinePartial2D(good0, good1)
    if M is None:
        return None
    a, b = M[0, 0], M[0, 1]
    tx, ty = M[0, 2], M[1, 2]
    scale = float(np.hypot(a, b))
    rot = float(np.degrees(np.arctan2(b, a)))
    flow = np.linalg.norm(good1 - good0, axis=1)
    mag = float(np.mean(flow))
    inlier = float(np.mean(inliers)) if inliers is not None else 0.0
    return {"scale": scale, "rot": rot, "tx": tx, "ty": ty,
            "mag": mag, "inlier": inlier, "n": len(good0)}


def _diff_pct(a: np.ndarray, b: np.ndarray, tol: int = 25) -> float:
    """Percent of pixels whose absolute change exceeds `tol` (0-255)."""
    return float(np.mean(cv2.absdiff(a, b) > tol)) * 100.0


def _circular_variance(unit_vectors: list[tuple[float, float]]) -> float:
    """0 = every frame moves in the same direction; 1 = directions scatter.
    A pan has near-0 variance; a handheld/shaky camera is much higher."""
    if not unit_vectors:
        return 0.0
    xs = np.array([u[0] for u in unit_vectors], dtype=float)
    ys = np.array([u[1] for u in unit_vectors], dtype=float)
    mean_len = float(np.hypot(np.mean(xs), np.mean(ys)))
    return float(min(1.0, 1.0 - mean_len))


# --- classification -------------------------------------------------------------

def classify_shot(net_tx: float, net_ty: float, mean_scale_minus1: float,
                  avg_mag: float, jitter: float,
                  static_pct: float, zoom_thr: float, jitter_thr: float) -> str:
    """Map accumulated per-shot motion into a camera-move label.

    `net_tx`/`net_ty` are total translation as a fraction of frame width/height
    (sign follows pixel motion, so a camera pan-right pushes pixels left).
    `mean_scale_minus1` is mean per-frame scale drift (>0 = content grows =
    camera zooms in). `avg_mag` is mean motion in %W/s. `jitter` is the circular
    variance of per-frame motion direction (0..1).
    """
    if avg_mag < static_pct:
        return "static"
    # Zoom: coherent scale change with little net translation.
    if abs(mean_scale_minus1) > zoom_thr and (abs(net_tx) + abs(net_ty)) < 0.04:
        return "zoom-in" if mean_scale_minus1 > 0 else "zoom-out"
    # Handheld: lots of motion but no consistent direction (high jitter).
    if jitter > jitter_thr:
        return "handheld"
    # Pan / tilt by the dominant axis of net translation.
    if abs(net_tx) >= abs(net_ty):
        # pixels moving left (tx<0) => camera panning right
        return "pan-right" if net_tx < 0 else "pan-left"
    return "tilt-down" if net_ty < 0 else "tilt-up"


def motion_label(avg_mag: float, low_pct: float, high_pct: float) -> str:
    if avg_mag >= high_pct:
        return "high"
    if avg_mag >= low_pct:
        return "medium"
    return "low"


# --- main entry -----------------------------------------------------------------

def analyze_motion(video: str, frames_dir: str, out_dir: str, duration: int,
                   *, motion_fps: float = 5.0, burst_interval: float = 0.2,
                   max_burst_frames: int = 12,
                   high_motion_pct: float = 8.0, low_motion_pct: float = 2.0,
                   static_pct: float = 1.0, zoom_thr: float = 0.008,
                   jitter_thr: float = 0.5, cut_min_pct: float = 40.0,
                   chapters: bool = False,
                   transcript_segments: list[dict] | None = None) -> dict:
    """Run the full motion analysis. Writes burst frames into `frames_dir` and a
    machine-readable `motion.json` into `out_dir`. Returns a dict with the
    manifest text lines (`text`), the structured `json`, the list of burst
    filenames (`bursts`), and optional `chapters`."""
    _require_cv2()

    tmp = os.path.join(out_dir, "_motion")
    os.makedirs(tmp, exist_ok=True)
    w = 160
    _run(["ffmpeg", "-y", "-i", video, "-vf", f"fps={motion_fps},scale={w}:-1",
          "-vsync", "vfr", os.path.join(tmp, "m_%05d.jpg"),
          "-hide_banner", "-loglevel", "error"])
    fpaths = sorted(glob.glob(os.path.join(tmp, "m_*.jpg")))
    n = len(fpaths)
    if n < 2:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"text": ["--- motion analysis --", "(skipped: video too short to estimate motion)"],
                "json": {"shots": [], "rhythm": {}}, "bursts": [], "chapters": []}

    fps = motion_fps
    grays = [_load_gray(p, w=w) for p in fpaths]
    grays = [g for g in grays if g is not None]
    W = grays[0].shape[1]

    diffs, moves = [], []
    for i in range(len(grays) - 1):
        d = _diff_pct(grays[i], grays[i + 1])
        diffs.append(d)
        m = _global_motion(grays[i], grays[i + 1])
        moves.append(m)  # may be None

    # Shot boundaries: a cut is a frame where the content jumps. The reliable
    # signal is *incoherence* — a hard cut can't be explained by a single global
    # transform, so the affine estimate's inlier ratio collapses. Fast motion
    # within a shot (a pan, a handheld shake) still tracks points coherently, so
    # its inlier stays high and it isn't mistaken for a cut. We also catch a cut
    # that is an extreme relative outlier in raw difference.
    med = float(np.median(diffs)) if diffs else 0.0
    cuts = []
    for i, (d, m) in enumerate(zip(diffs, moves)):
        incoherent = (m is None) or (m["inlier"] < 0.4)
        if (d > cut_min_pct and incoherent) or d > max(60.0, 5.0 * med):
            cuts.append(i)
    # shot index ranges: [start, end) over frame indices
    bounds = [0] + [c + 1 for c in cuts] + [len(grays)]
    shots = []
    for s, e in zip(bounds[:-1], bounds[1:]):
        if e <= s:
            continue
        seg_moves = [m for m in moves[s:e - 1] if m is not None]
        if not seg_moves:
            shots.append({"start": s / fps, "end": e / fps,
                          "camera": "static", "motion": "low", "mag": 0.0,
                          "jitter": 0.0, "bursts": []})
            continue
        tx = sum(m["tx"] for m in seg_moves) / W
        ty = sum(m["ty"] for m in seg_moves) / grays[0].shape[0]
        mean_scale = float(np.mean([m["scale"] - 1 for m in seg_moves]))
        avg_mag = float(np.mean([m["mag"] / W * 100 * fps for m in seg_moves]))
        moving = [m for m in seg_moves if m["mag"] > 0.5]
        units = []
        for m in moving:
            ang = np.arctan2(-m["ty"], -m["tx"])  # pixel-flow direction
            units.append((float(np.cos(ang)), float(np.sin(ang))))
        jitter = _circular_variance(units) if units else 0.0
        cam = classify_shot(tx, ty, mean_scale, avg_mag, jitter,
                            static_pct, zoom_thr, jitter_thr)
        lvl = motion_label(avg_mag, low_motion_pct, high_motion_pct)
        shots.append({"start": s / fps, "end": e / fps, "camera": cam,
                      "motion": lvl, "mag": round(avg_mag, 1),
                      "jitter": round(jitter, 2), "bursts": []})

    # Action bursts: high-motion shots get extra 0.2s-apart frames at full res.
    bursts = []
    burst_fps = 1.0 / max(0.05, burst_interval)
    for idx, shot in enumerate(shots, 1):
        if shot["motion"] != "high":
            continue
        dur = shot["end"] - shot["start"]
        if dur <= 0:
            continue
        cnt = min(max_burst_frames, max(2, int(round(dur / burst_interval)) + 1))
        prefix = f"burst_shot{idx:02d}"
        pat = os.path.join(frames_dir, f"{prefix}_%02d.jpg")
        _run(["ffmpeg", "-y", "-ss", f"{shot['start']:.3f}", "-i", video,
              "-t", f"{dur:.3f}", "-vf", f"fps={burst_fps:.2f},scale=640:-1",
              pat, "-hide_banner", "-loglevel", "error"])
        files = sorted(glob.glob(os.path.join(frames_dir, f"{prefix}_*.jpg")))
        if not files:
            continue
        for f in files[cnt:]:
            os.remove(f)
        files = files[:cnt]
        names = [os.path.basename(f) for f in files]
        shot["bursts"] = names
        bursts.extend(names)

    # Editing rhythm
    durs = [round(shot["end"] - shot["start"], 2) for shot in shots]
    total_dur = float(sum(durs)) or float(duration or 0)
    cuts_min = round((len(shots) - 1) / total_dur * 60, 1) if total_dur > 0 else 0.0
    if durs:
        avg = round(sum(durs) / len(durs), 1)
        med = round(float(np.median(durs)), 1)
        rng = f"{min(durs)}-{max(durs)}s"
    else:
        avg = med = 0.0
        rng = "0-0s"
    thirds = [0, 0, 0]
    for shot in shots:
        t = shot["start"] / total_dur if total_dur > 0 else 0
        thirds[min(2, int(t * 3))] += 1

    rhythm = {"shots": len(shots), "cuts_per_min": cuts_min,
              "avg": avg, "median": med, "range": rng,
              "thirds": {"open": thirds[0], "middle": thirds[1], "close": thirds[2]}}

    # Build manifest text
    lines = ["--- motion analysis --"]
    lines.append(
        f"editing rhythm: {len(shots)} shots | {cuts_min} cuts/min | "
        f"avg {avg}s (median {med}s, range {rng})")
    lines.append(f"cuts by thirds (open/middle/close): {thirds[0]} / {thirds[1]} / {thirds[2]}")
    lines.append("shots:")
    for idx, shot in enumerate(shots, 1):
        start, end = shot["start"], shot["end"]
        sdur = end - start
        burst = ""
        if shot["bursts"]:
            b0, b1 = shot["bursts"][0], shot["bursts"][-1]
            burst = f" burst: {b0}..{b1}" if b0 != b1 else f" burst: {b0}"
        lines.append(
            f"  #{idx:02d}  {start:05.2f}-{end:05.2f}s  ({sdur:04.2f}s) "
            f"camera: {shot['camera']:<9} motion: {shot['motion']} "
            f"({shot['mag']}%W/s){burst}")

    # Optional chapters (reuses the shot boundaries)
    chap = []
    if chapters:
        chap = _build_chapters(shots, transcript_segments, target=8)
        if chap:
            lines.append("chapters:")
            for c in chap:
                lines.append(f"  {c['start']:05.2f}s  {c['title']}")

    payload = {"rhythm": rhythm, "shots": shots,
               "chapters": chap, "settings": {
                   "motion_fps": motion_fps, "burst_interval": burst_interval,
                   "high_motion_pct": high_motion_pct}}
    json_path = os.path.join(out_dir, "motion.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    shutil.rmtree(tmp, ignore_errors=True)
    return {"text": lines, "json": payload, "bursts": bursts, "chapters": chap,
            "json_path": json_path}


def _build_chapters(shots: list[dict], segments: list[dict] | None,
                    target: int = 8) -> list[dict]:
    """Group shots into ~`target` chapters by duration and label each by the
    transcript text spoken at its start (or by its dominant camera move)."""
    if not shots:
        return []
    total = sum(s["end"] - s["start"] for s in shots) or 1.0
    step = total / target
    chapters, cur = [], []
    acc = 0.0
    for shot in shots:
        cur.append(shot)
        acc += shot["end"] - shot["start"]
        if acc >= step or shot is shots[-1]:
            start = cur[0]["start"]
            end = cur[-1]["end"]
            title = _label_for(start, cur, segments)
            chapters.append({"start": round(start, 2), "end": round(end, 2),
                             "title": title})
            cur, acc = [], 0.0
    return chapters


def _label_for(start: float, shots: list[dict], segments: list[dict] | None) -> str:
    if segments:
        for seg in segments:
            if seg["start"] <= start < seg["end"]:
                words = " ".join(seg["text"].split()[:8])
                return (words + ("…" if len(seg["text"].split()) > 8 else "")).strip()
    moves = ", ".join(sorted({s["camera"] for s in shots}))
    return f"[{moves}] @ {start:.0f}s"


# --- --poster: a single representative thumbnail --------------------------------

def extract_poster(frames_dir: str, out_dir: str, video: str,
                   duration: int, scale_w: int = 640) -> str | None:
    """Pick the most informative kept frame as a lead thumbnail (`poster.jpg`).

    Scores each kept frame by sharpness (Laplacian variance) and local contrast;
    the winner best represents the video to an LLM that reads frames in order.
    Falls back to the video's middle frame when no kept frames exist."""
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    best, best_score = None, -1.0
    for f in frames:
        im = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        im = cv2.resize(im, (320, int(320 * im.shape[0] / im.shape[1])))
        score = float(cv2.Laplacian(im, cv2.CV_64F).var()) + 0.01 * float(im.std())
        if score > best_score:
            best_score, best = score, f
    if best is None:
        if duration <= 0:
            return None
        _run(["ffmpeg", "-y", "-ss", f"{duration / 2:.3f}", "-i", video,
              "-frames:v", "1", "-vf", f"scale={scale_w}:-1",
              os.path.join(out_dir, "poster.jpg"),
              "-hide_banner", "-loglevel", "error"])
    else:
        shutil.copy(best, os.path.join(out_dir, "poster.jpg"))
    return os.path.join(out_dir, "poster.jpg") if os.path.exists(
        os.path.join(out_dir, "poster.jpg")) else None
