"""The slow-motion scan must honour --from/--to like every other stage.

Before 0.10.6 it decoded the whole file frame by frame regardless of the window.
Measured on 2026-09-19: analysing a 3-minute window of a 19-minute source spent
347s of a 350s run inside this one check; passing the window through cut the same
command from 369s to 77s with byte-identical output.
"""
from unittest import mock

from claude_real_video import temporal_check


def _args_for(**kw):
    """Run temporal_hint with subprocess stubbed out and return the argv it built."""
    fake = mock.Mock(stdout="", stderr="")
    with mock.patch.object(temporal_check.subprocess, "run", return_value=fake) as run:
        temporal_check.temporal_hint("clip.mp4", **kw)
    return run.call_args[0][0]


def test_a_window_is_passed_to_ffmpeg_before_the_input():
    argv = _args_for(start=60.0, end=240.0)
    assert "-ss" in argv and "-t" in argv
    # Input-side seek: both must come before -i or ffmpeg decodes from zero anyway.
    assert argv.index("-ss") < argv.index("-i")
    assert argv.index("-t") < argv.index("-i")
    assert argv[argv.index("-ss") + 1] == "60.000"
    assert argv[argv.index("-t") + 1] == "180.000"   # duration, not end time


def test_a_start_only_window_has_no_duration_cap():
    argv = _args_for(start=90.0)
    assert argv[argv.index("-ss") + 1] == "90.000"
    assert "-t" not in argv


def test_an_end_only_window_caps_duration_from_zero():
    argv = _args_for(end=45.0)
    assert argv[argv.index("-t") + 1] == "45.000"
    assert "-ss" not in argv


def test_no_window_scans_the_whole_file_as_before():
    argv = _args_for()
    assert "-ss" not in argv and "-t" not in argv
    assert argv[argv.index("-i") + 1] == "clip.mp4"


def test_the_pipeline_hands_its_window_to_the_check():
    """core.process must forward start/end; the bug was that it called with neither."""
    import inspect
    from claude_real_video import core
    src = inspect.getsource(core)
    assert "temporal_hint(video, start=start, end=end)" in src, \
        "core stopped forwarding the window to temporal_hint"
