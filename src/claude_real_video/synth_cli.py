"""viralsynth CLI — analyse a viral video, then generate a new one from the
motion blueprint.

Pipeline:
  1. analyse  : `crv <source> --motion` (scene-aware frames + camera/rhythm)
  2. plan     : pull matching segments (clone) or write a narration (breakdown)
  3. render   : local ffmpeg assembles the new video

Run `viralsynth "<url>" --topic "..."` and it does all three.
"""
import argparse
import os
import sys

from .synthesis import (load_blueprint, build_candidate_pool, render_clone,
                        render_breakdown)
from .llm import get_llm


def _collect_assets(paths: list[str]) -> list[str]:
    out = []
    for p in paths or []:
        if os.path.isdir(p):
            for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
                out.extend(sorted(os.path.join(p, f) for f in os.listdir(p)
                                  if f.lower().endswith(ext)))
        elif os.path.exists(p):
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="viralsynth",
        description="Analyse a viral YouTube/TikTok video, then generate a new "
                    "video from its motion blueprint (clone = style remix, "
                    "breakdown = narrated teardown).")
    ap.add_argument("source", help="Viral video URL (YouTube/TikTok/...) or local file")
    ap.add_argument("-o", "--out", default="viralsynth_out.mp4",
                    help="Output video path (default: ./viralsynth_out.mp4)")
    ap.add_argument("--analyze-out", default=None,
                    help="Reuse an existing crv --motion output dir instead of "
                         "re-analysing (must contain motion.json)")
    ap.add_argument("--mode", choices=["clone", "breakdown"], default="clone",
                    help="clone = remix in the viral style from matching segments; "
                         "breakdown = narrated teardown of the viral video")
    ap.add_argument("--topic", default="your topic",
                    help="Theme/reframe the generated video is about")
    ap.add_argument("--assets", nargs="*", default=[],
                    help="Extra video file(s) or folder(s) to pull segments from "
                         "(the source video is always included)")
    ap.add_argument("--transcribe", action="store_true",
                    help="Transcribe audio during analysis (needs whisper). Off by "
                         "default to stay fast; breakdown narration works without it")
    ap.add_argument("--llm", default="auto",
                    choices=["auto", "claude", "openai", "local", "none"],
                    help="LLM for on-screen copy / narration (default: auto-detect)")
    ap.add_argument("--llm-model", default=None, help="Override the LLM model id")
    ap.add_argument("--tts", action="store_true",
                    help="(breakdown) add voiceover via local TTS if available")
    ap.add_argument("--pool-step", type=float, default=3.0,
                    help="Seconds between candidate-pool windows (default: 3.0)")
    ap.add_argument("--pool-len", type=float, default=3.0,
                    help="Candidate window length in seconds (default: 3.0)")
    ap.add_argument("--width", type=int, default=1080, help="Output width (default 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Output height (default 1920)")
    args = ap.parse_args()

    try:
        # 1) analyse (or reuse)
        if args.analyze_out and os.path.exists(os.path.join(args.analyze_out, "motion.json")):
            out_dir = args.analyze_out
            print(f"[1/3] reuse analysis: {out_dir}")
        else:
            from .core import process
            out_dir = args.out + ".crv"
            print(f"[1/3] analysing {args.source} -> {out_dir}")
            process(args.source, out_dir, motion=True,
                    do_transcribe=args.transcribe,
                    why=f"blueprint for viralsynth ({args.mode})")
        blueprint = load_blueprint(out_dir)
        print(f"      blueprint: {len(blueprint.shots)} shots | "
              f"{blueprint.rhythm.get('cuts_per_min', 0)} cuts/min")

        # 2) + 3) plan + render
        llm = get_llm(args.llm, args.llm_model)
        assets = [blueprint.source_video] + _collect_assets(args.assets)
        if args.mode == "clone":
            print(f"[2/3] building candidate pool from {len(assets)} video(s)...")
            cands = build_candidate_pool(assets, pool_step=args.pool_step,
                                         pool_len=args.pool_len)
            print(f"      {len(cands)} candidate segments")
            print(f"[3/3] rendering clone -> {args.out}")
            res = render_clone(blueprint, cands, args.out, llm, args.topic,
                               w=args.width, h=args.height)
        else:
            print(f"[3/3] rendering breakdown -> {args.out}")
            res = render_breakdown(blueprint, args.out, llm, args.topic,
                                   w=args.width, h=args.height, tts=args.tts)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Done → {res['out']}")
    print(f"  segments: {res['segments']}")
    print(f"  plan:     {res['plan_path']}")


if __name__ == "__main__":
    main()
