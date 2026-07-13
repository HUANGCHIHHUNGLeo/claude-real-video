"""Minimal smoke tests: the package imports and the CLI answers --help."""

import subprocess
import sys


def test_import():
    import claude_real_video

    assert hasattr(claude_real_video, "process")


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "claude_real_video", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "crv" in result.stdout.lower() or "video" in result.stdout.lower()


def test_parse_showinfo_times():
    from claude_real_video.core import _parse_showinfo_times, _fmt_ts

    stderr = (
        "[Parsed_showinfo_1 @ 0x7f8] n:   0 pts:      0 pts_time:0       duration_time:0.04\n"
        "[Parsed_showinfo_1 @ 0x7f8] n:   1 pts:   4600 pts_time:18.42   duration_time:0.04\n"
        "[Parsed_showinfo_1 @ 0x7f8] n:   2 pts:  90000 pts_time:360.001 duration_time:0.04\n"
    )
    assert _parse_showinfo_times(stderr) == [0.0, 18.42, 360.001]
    assert _fmt_ts(18.42) == "00:00:18.420"
    assert _fmt_ts(3661.5) == "01:01:01.500"


def test_frames_json_end_to_end(tmp_path):
    """Full pipeline on a tiny generated video: frames.json must map every kept
    frame to a plausible, strictly increasing source timestamp (issue #7)."""
    import json
    import shutil as _sh

    if not (_sh.which("ffmpeg") and _sh.which("ffprobe")):
        import pytest
        pytest.skip("ffmpeg not installed")
    src = tmp_path / "src.mp4"
    # 6s test pattern with a hard cut every 2s (three distinct scenes)
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
         "-f", "lavfi", "-i", "smptebars=duration=2:size=320x240:rate=10",
         "-f", "lavfi", "-i", "rgbtestsrc=duration=2:size=320x240:rate=10",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]",
         str(src)], capture_output=True)
    out = tmp_path / "out"
    from claude_real_video import process

    r = process(str(src), str(out), do_transcribe=False)
    assert r.frames_json_path and (out / "frames.json").exists()
    data = json.load(open(r.frames_json_path, encoding="utf-8"))
    files = sorted(p.name for p in (out / "frames").glob("*.jpg"))
    assert [f["file"] for f in data["frames"]] == files
    secs = [f["timestamp_sec"] for f in data["frames"]]
    assert all(b > a for a, b in zip(secs, secs[1:]))  # strictly increasing
    assert all(0 <= s <= 6.5 for s in secs)
    assert all(f["timestamp"].count(":") == 2 for f in data["frames"])
