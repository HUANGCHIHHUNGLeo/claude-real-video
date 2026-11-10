"""A WEBVTT file header must not leak into transcript.txt.

Platform captions (the URL path, 0.10.2 onward) arrive as .vtt whose header
block is `WEBVTT` / `Kind: captions` / `Language: en`. `_subs_to_text` dropped
only the `WEBVTT` line, so the other two headers were written out as if they
were the video's first two spoken lines. Everything before the first timecode
is file header by spec, so that is what we skip — which also covers NOTE /
STYLE / REGION and any future header key, without touching cue text.
"""
import pytest

from claude_real_video.core import _subs_to_text

VTT = """WEBVTT
Kind: captions
Language: en

00:00:04.220 --> 00:00:05.400
This is a 3.

00:00:06.060 --> 00:00:10.713
It's sloppily written<00:00:07.000><c> and</c> rendered small,

00:00:10.713 --> 00:00:13.720
but your brain has no trouble with it.
"""

SRT = """1
00:00:01,000 --> 00:00:02,000
Hello world

2
00:00:03,000 --> 00:00:04,000
Second line
"""


def _text(tmp_path, body, name):
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    out = tmp_path / "transcript.txt"
    assert _subs_to_text(str(src), str(out)) == str(out)
    return out.read_text(encoding="utf-8")


def test_vtt_header_never_reaches_the_transcript(tmp_path):
    lines = _text(tmp_path, VTT, "source.en.vtt").splitlines()
    assert lines[0] == "This is a 3."          # first spoken line survives
    for header in ("WEBVTT", "Kind:", "Language:"):
        assert not any(l.startswith(header) for l in lines), lines
    assert len(lines) == 3                      # three cues, three lines
    assert lines[1] == "It's sloppily written and rendered small,"  # tags gone


def test_header_keys_we_have_not_seen_yet_are_also_skipped(tmp_path):
    body = VTT.replace("Kind: captions", "NOTE this file was machine-made\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000")
    lines = _text(tmp_path, body, "odd.vtt").splitlines()
    assert lines[0] == "This is a 3."
    assert len(lines) == 3


def test_srt_is_unchanged(tmp_path):
    # No header block to skip — the cue indices were, and stay, dropped.
    assert _text(tmp_path, SRT, "sidecar.srt") == "Hello world\nSecond line\n"


def test_digit_only_cue_text_is_kept_and_indices_are_not(tmp_path):
    """A line of digits after a timecode is the caption, not the next index.

    The index is the digit line *between* cues. Dropping every all-digit line
    once a cue has been seen also deletes a code, a year, or a countdown that
    is the whole cue — and a second line of the same cue that is only a number.
    """
    body = """1
00:00:01,000 --> 00:00:02,000
The code is

2
00:00:02,000 --> 00:00:03,500
4821

3
00:00:04,000 --> 00:00:05,000
pin
90210

4
00:00:06,000 --> 00:00:07,000
remember it
"""
    assert _text(tmp_path, body, "code.srt") == (
        "The code is\n4821\npin\n90210\nremember it\n")


def test_vtt_digit_only_cue_is_kept(tmp_path):
    body = """WEBVTT

00:00:01.000 --> 00:00:02.000
3

00:00:02.000 --> 00:00:03.000
go
"""
    assert _text(tmp_path, body, "count.vtt") == "3\ngo\n"


def test_a_file_with_no_cues_yields_nothing(tmp_path):
    src = tmp_path / "headers_only.vtt"
    src.write_text("WEBVTT\nKind: captions\nLanguage: en\n", encoding="utf-8")
    assert _subs_to_text(str(src), str(tmp_path / "t.txt")) is None
