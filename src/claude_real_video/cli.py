"""Command-line interface for claude-real-video."""
import argparse
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
    ap.add_argument("--scene", type=float, default=0.30,
                    help="Scene-change sensitivity 0-1, lower = more frames (default: 0.30)")
    ap.add_argument("--fps-floor", type=float, default=1.0,
                    help="Guarantee at least one frame every N seconds (default: 1.0)")
    ap.add_argument("--max-frames", type=int, default=150, help="Cap total frames (default: 150)")
    ap.add_argument("--lang", default="auto", help="Whisper language, e.g. en / zh / auto (default: auto)")
    ap.add_argument("--cookies", default=None,
                    help="Netscape cookie file for sites that need login (your own, authorised use only)")
    ap.add_argument("--no-transcribe", action="store_true", help="Skip audio transcription")
    ap.add_argument("--whisper-model", default="base",
                    choices=["tiny", "base", "small", "medium", "large"],
                    help="Whisper model for transcription (default: base — fast; "
                         "pick medium/large for tricky audio, they download more and run slower)")
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
            scene=args.scene, fps_floor=args.fps_floor, max_frames=args.max_frames,
            lang=args.lang, cookies=args.cookies,
            do_transcribe=not args.no_transcribe,
            whisper_model=args.whisper_model, dedup_threshold=args.dedup_threshold,
            dedup_window=args.dedup_window, keep_audio=args.keep_audio, report=args.report,
            why=args.why,
        )
    except Exception as e:  # noqa: BLE001 — surface a clean message to the user
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Done → {r.out_dir}")
    print(f"  {r.frame_count} frames  (deduped from {r.extracted_frames} extracted)  in {r.frames_dir}")
    print(f"  manifest:   {r.manifest_path}")
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


if __name__ == "__main__":
    main()
