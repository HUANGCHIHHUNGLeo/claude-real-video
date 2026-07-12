"""Command-line interface for claude-real-video."""
import argparse
import os
import sys

from .core import process


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="claude-real-video",
        description="Let Claude (or any LLM) actually watch a video: scene-aware, "
                    "deduplicated frames + a transcript, from a URL or a local file.",
    )
    ap.add_argument("source", help="Video URL (YouTube, Instagram, ...) or a local file path")
    ap.add_argument("-o", "--out", default="crv-out", help="Output directory (default: ./crv-out)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Replace a previous analysis living in the output directory "
                         "(without this, a non-empty output dir is refused to avoid mixing videos)")
    ap.add_argument("--scene", type=float, default=0.30,
                    help="Scene-change sensitivity 0-1, lower = more frames (default: 0.30)")
    ap.add_argument("--fps-floor", type=float, default=1.0,
                    help="Guarantee at least one frame every N seconds (default: 1.0)")
    ap.add_argument("--max-frames", type=int, default=150, help="Cap total frames (default: 150)")
    ap.add_argument("--adaptive", action="store_true",
                    help="Adaptive scene detection: catches slow morphs (2-3s squash/stretch, "
                         "gradual pans) a fixed threshold misses, by comparing each frame "
                         "against its rolling neighbourhood instead of a constant")
    ap.add_argument("--text-anchors", action="store_true",
                    help="Force extra frames at subtitle-cue timestamps (sidecar .srt/.vtt "
                         "or embedded track) — for videos where meaning changes faster than "
                         "pixels: burned-in captions, lecture slides, screen recordings. "
                         "At most one forced frame per second; scene detection unchanged")
    ap.add_argument("--lang", default="auto", help="Whisper language, e.g. en / zh / auto (default: auto)")
    ap.add_argument("--cookies", default=None,
                    help="Netscape cookie file for sites that need login (your own, authorised use only)")
    ap.add_argument("--cookies-from-browser", default=None, metavar="BROWSER",
                    help="read login cookies straight from your own browser — chrome, safari, "
                         "firefox or edge. For sites that need login (your own account only)")
    ap.add_argument("--no-transcribe", action="store_true", help="Skip audio transcription")
    ap.add_argument("--viewer", action="store_true",
                    help="also write viewer.html — browse the video, keyframes and "
                         "transcript in one local page (double-click to open)")
    ap.add_argument("--whisper-model", default="base",
                    choices=["tiny", "base", "small", "medium", "large", "turbo"],
                    help="Whisper model for transcription (default: base — fast; "
                         "pick turbo for large-v3 accuracy at ~8x large's speed, "
                         "medium/large also available — bigger models download more)")
    ap.add_argument("--dedup-threshold", type=float, default=8,
                    help="Percent of pixels that must change for a frame to count as new; "
                         "higher = fewer frames kept (default: 8)")
    ap.add_argument("--dedup-window", type=int, default=4,
                    help="Compare each frame against the last N kept frames, so a shot "
                         "the model already saw doesn't come back after a cutaway "
                         "(1 = classic consecutive-only, default: 4)")
    ap.add_argument("--report", action="store_true",
                    help="Keep dropped frames in ./dropped and write report.html "
                         "visualising every keep/drop decision, for tuning the threshold")
    ap.add_argument("--why", default=None,
                    help='Why you are watching, e.g. --why "find the pricing strategy" — '
                         "written into MANIFEST.txt so the model analyses with that lens "
                         "instead of producing a generic summary")
    ap.add_argument("--grid", action="store_true",
                    help="Also tile the kept frames into 3x3 contact sheets (./grids) — "
                         "consecutive frames side by side help the model follow motion "
                         "and progression instead of guessing between stills")
    ap.add_argument("--kb", default=None, metavar="DIR",
                    help="Also save the analysis as a dated markdown note into this "
                         "knowledge-base folder (e.g. your Obsidian vault)")
    ap.add_argument("--keep-audio", action="store_true",
                    help="Also save the full original soundtrack (music + speech) as audio.m4a, "
                         "for models that can listen to audio (Gemini, GPT-4o, ...)")
    args = ap.parse_args()

    try:
        r = process(
            args.source, args.out,
            scene=args.scene, adaptive=args.adaptive, text_anchors=args.text_anchors,
            fps_floor=args.fps_floor, max_frames=args.max_frames,
            lang=args.lang, cookies=args.cookies, cookies_from_browser=args.cookies_from_browser,
            do_transcribe=not args.no_transcribe,
            whisper_model=args.whisper_model, dedup_threshold=args.dedup_threshold,
            dedup_window=args.dedup_window, keep_audio=args.keep_audio, report=args.report,
            why=args.why, overwrite=args.overwrite,
        )
    except Exception as e:  # noqa: BLE001 — surface a clean message to the user
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Done → {r.out_dir}")
    print(f"  {r.frame_count} frames  (deduped from {r.extracted_frames} extracted)  in {r.frames_dir}")
    print(f"  manifest:   {r.manifest_path}")
    if args.viewer:
        from .viewer import write_viewer
        vsrc = os.path.join(r.out_dir, "source.mp4")
        vp = write_viewer(r.out_dir, vsrc if os.path.exists(vsrc) else (args.source if os.path.exists(args.source) else None))
        print(f"  viewer:     {vp}  (double-click to open)")
    if r.report_path:
        print(f"  report:     {r.report_path}  (open in a browser to tune the threshold)")
    if r.transcript_path:
        print(f"  transcript: {r.transcript_path}")
    else:
        print(f"  transcript: {r.transcript_note}")
    if r.audio_path:
        print(f"  audio:      {r.audio_path}  (full soundtrack — music + speech)")
    if args.grid:
        from .core import make_grids
        sheets = make_grids(r.frames_dir, r.out_dir)
        print(f"  grids:      {len(sheets)} contact sheet(s) in {r.out_dir}/grids")
    if args.kb:
        from .core import save_to_kb
        dest = save_to_kb(args.kb, r.manifest_path, args.source)
        print(f"  knowledge base: {dest}")
    # one quiet pointer, opt out with CRV_NO_HINT=1
    if not os.environ.get("CRV_NO_HINT"):
        print("  pro:        camera-motion + voice-emotion analysis → https://leoaido.com/crv-pro/")


if __name__ == "__main__":
    main()
