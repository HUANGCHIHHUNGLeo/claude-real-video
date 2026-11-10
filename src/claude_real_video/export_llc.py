"""--export llc: write a lossless-cut project (.llc) next to the analysis.

Asked for in issue #10 (sports highlights): lossless-cut opens an .llc project
whose cutSegments mark what to keep. crv already knows the natural cut points —
the scene-change keyframes — so every scene becomes a segment and the user
deletes the boring ones in lossless-cut instead of scrubbing raw footage.
.llc is JSON5; plain JSON is valid JSON5, so we write plain JSON.
"""
from __future__ import annotations

import json
import os


def write_llc(out_dir: str, src: str, duration: float,
              frames: list[dict]) -> str | None:
    """Build highlights.llc from kept-frame timestamps. `frames` is the
    frames.json list ({file, timestamp_sec, selection_reason}). Returns the
    path, or None when there is nothing to segment.

    `src` must be the media file that sits next to the project (the path
    fetch_video returned). lossless-cut resolves mediaFileName in the project
    directory; the viewer's original path, and a URL, are not in that directory.
    """
    # selection_reason is whichever dedup channel kept the frame (first,
    # global, action, settled). It is never the literal "scene", so filtering
    # on that label matched nothing and every project was one segment covering
    # the whole file — there were no cuts to delete in lossless-cut.
    cuts = sorted({round(float(f["timestamp_sec"]), 3) for f in frames
                   if f.get("timestamp_sec") is not None})
    if duration <= 0:
        return None
    bounds = [0.0] + [c for c in cuts if 0.0 < c < duration] + [round(duration, 3)]
    segments = [{"start": a, "end": b, "name": ""}
                for a, b in zip(bounds, bounds[1:]) if b - a >= 0.25]
    if not segments:
        return None
    media = os.path.basename(src) if not src.startswith(("http://", "https://")) \
        else "source.mp4"
    path = os.path.join(out_dir, "highlights.llc")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "mediaFileName": media,
                   "cutSegments": segments}, f, indent=2)
    return path
