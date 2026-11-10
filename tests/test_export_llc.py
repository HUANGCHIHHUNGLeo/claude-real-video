"""--export llc must mark the kept frames and name the file next to the project.

Two measured failures on a local recording:

* selection_reason is the dedup channel (first/global/action/settled), never
  the literal "scene", so the old filter matched nothing and highlights.llc
  was a single segment from 0 to the end. lossless-cut opened one clip with
  nothing to delete.
* process() handed write_llc the original path. The project lives in the
  output directory next to source.mp4 (the copy/download); the original
  basename is not there, so lossless-cut could not find the media.
"""
import inspect
import json

from claude_real_video import core
from claude_real_video.export_llc import write_llc


FRAMES = [
    {"file": "frame_001.jpg", "timestamp_sec": 0.0, "selection_reason": "first"},
    {"file": "frame_002.jpg", "timestamp_sec": 4.2, "selection_reason": "global"},
    {"file": "frame_003.jpg", "timestamp_sec": 12.8, "selection_reason": "action"},
    {"file": "frame_004.jpg", "timestamp_sec": 30.0, "selection_reason": "settled"},
]


def test_kept_frames_become_cut_segments(tmp_path):
    media = tmp_path / "source.mp4"
    path = write_llc(str(tmp_path), str(media), 40.0, FRAMES)
    data = json.loads((tmp_path / "highlights.llc").read_text(encoding="utf-8"))
    assert path == str(tmp_path / "highlights.llc")
    assert data["mediaFileName"] == "source.mp4"
    assert data["cutSegments"] == [
        {"start": 0.0, "end": 4.2, "name": ""},
        {"start": 4.2, "end": 12.8, "name": ""},
        {"start": 12.8, "end": 30.0, "name": ""},
        {"start": 30.0, "end": 40.0, "name": ""},
    ]


def test_non_mp4_download_is_named_as_written(tmp_path):
    # yt-dlp sometimes leaves source.webm when the mp4 mux does not happen.
    # Hardcoding source.mp4 would point lossless-cut at a file that is not there.
    path = write_llc(str(tmp_path), str(tmp_path / "source.webm"), 10.0, [
        {"file": "frame_001.jpg", "timestamp_sec": 3.0, "selection_reason": "global"},
    ])
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["mediaFileName"] == "source.webm"
    assert data["cutSegments"] == [
        {"start": 0.0, "end": 3.0, "name": ""},
        {"start": 3.0, "end": 10.0, "name": ""},
    ]


def test_process_passes_the_fetched_file_not_the_original_source():
    src = inspect.getsource(core.process)
    assert "write_llc(out_dir, video," in src
