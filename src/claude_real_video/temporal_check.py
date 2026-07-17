"""Simple temporal check (free tier) — pure ffmpeg, zero extra dependencies.

Reads per-frame luma difference (signalstats YDIF) and reports a one-line hint
ONLY when evidence is strong. Two signals, both calibrated on labeled clips
(2026-07-17):
- padded slow-motion: duplicate ratio > 0.5 arranged as MANY SHORT runs
  (true 4x padding measures ~0.75 with hundreds of 1-4 frame runs; a freeze
  frame shows ONE long run and is deliberately ignored — editing, not speed).
- interval capture was evaluated for this tier and moved to Pro-only: pure
  frame-difference stats cannot separate it from fast-action sports footage.

The Pro tier (crv Pro --speed-check) does multi-channel per-segment analysis;
this free check is a conservative single-signal hint and stays silent unless
confident. Never claims "normal speed".
"""

import re
import subprocess
import statistics


def temporal_hint(video_path, ffmpeg="ffmpeg"):
    """Return a one-line hint string, or None when no strong evidence.

    Free tier deliberately reports ONLY padded slow-motion. The interval-capture
    signal was tested and dropped here: fast-action wild footage (sports reels,
    parkour POV) is indistinguishable from moderate timelapse on frame-difference
    statistics alone (calibration 2026-07-17: basketball p25 luma-diff 10.8 vs
    real 8x lapse 5.7). Detecting it safely needs the Pro multi-channel analysis.
    """
    try:
        proc = subprocess.run(
            [ffmpeg, "-i", video_path, "-vf",
             "signalstats,metadata=print:key=lavfi.signalstats.YDIF:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=600)
        vals = [float(m) for m in re.findall(r"YDIF=([0-9.]+)", proc.stdout)]
    except Exception:
        return None
    if len(vals) < 24:
        return None

    # Padding precondition: when >50% of frames are duplicates (2x+ padding),
    # the MEDIAN luma-diff necessarily sits near zero. Calibration: padded clips
    # measure med 0.00-0.03; clean footage 2.2-3.7; a freeze-heavy edit (N) 0.26.
    med = statistics.median(vals)
    if med >= 0.2:
        return None
    # split an order of magnitude above the duplicate mode, capped for safety
    split = min(0.6, max(0.1, med * 10))
    dup = [v < split for v in vals]
    dup_ratio = sum(dup) / len(dup)

    runs = []
    r = 0
    for d in dup:
        if d:
            r += 1
        elif r:
            runs.append(r)
            r = 0
    if r:
        runs.append(r)

    # padded slow-motion: many short interleaved duplicate runs.
    # A single dominant long run is a freeze-frame (editing) and stays silent.
    if dup_ratio > 0.55 and len(runs) >= 20:
        med_run = statistics.median(runs)
        if max(runs) <= 4 * max(1, med_run):
            return ("temporal check: regular frame padding detected "
                    f"(duplicate ratio {dup_ratio:.0%} across {len(runs)} short runs) "
                    "— slowed-down footage suspected")
    return None
