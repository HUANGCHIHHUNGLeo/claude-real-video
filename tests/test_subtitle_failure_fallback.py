"""A caption fetch that fails must not sink the video download.

crv asks the platform for its own captions before downloading, because they beat
Whisper on speed and accuracy when they arrive. But platforms rate-limit caption
endpoints much harder than media, and a 429 there used to abort the whole run:
the subtitle flags rode along on every cookie retry, so all three attempts failed
identically and Whisper -- the documented fallback -- never got a file to work on.
The user saw a bare "Download failed", which points at the video, not the captions.
"""
import os

import pytest

import claude_real_video.core as core

SUB_429 = ("ERROR: Unable to download video subtitles for 'en': "
           "HTTP Error 429: Too Many Requests")


def _downloads(calls):
    """Only the download invocations: a failure also probes `yt-dlp --version`."""
    return [c for c in calls if "-o" in c]


def _fake_runner(err_for_subs, calls):
    """yt-dlp stand-in: fails while captions are requested, succeeds without them."""
    class R:
        def __init__(self, stderr):
            self.stderr, self.stdout = stderr, ""

    def run(cmd):
        calls.append(cmd)
        if "--write-subs" in cmd:
            return R(err_for_subs)
        with open(cmd[cmd.index("-o") + 1], "wb") as f:
            f.write(b"not really a video")
        return R("")
    return run


def test_caption_429_retries_without_captions(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(core, "_have", lambda tool: True)
    monkeypatch.setattr(core, "_run", _fake_runner(SUB_429, calls))

    got = core.fetch_video("https://example.com/v", str(tmp_path), sub_lang="en")

    assert os.path.exists(got)
    assert [("--write-subs" in c) for c in _downloads(calls)] == [True, False]


def test_cookie_retries_stop_requesting_captions(tmp_path, monkeypatch):
    """The regression that made a transient 429 fatal: every retry repeated it."""
    calls = []
    monkeypatch.setattr(core, "_have", lambda tool: True)
    # Nothing ever succeeds here, so all attempts run and can be inspected.
    monkeypatch.setattr(core, "_run", lambda cmd: calls.append(cmd) or type(
        "R", (), {"stderr": SUB_429, "stdout": ""})())

    with pytest.raises(RuntimeError):
        core.fetch_video("https://example.com/v", str(tmp_path),
                         cookies="ck.txt", sub_lang="en")

    assert [("--write-subs" in c) for c in _downloads(calls)] == [True, False, False]


def test_real_error_is_not_retried(tmp_path, monkeypatch):
    """A genuine failure must surface on the first attempt, unmasked."""
    calls = []
    monkeypatch.setattr(core, "_have", lambda tool: True)
    monkeypatch.setattr(core, "_run", lambda cmd: calls.append(cmd) or type(
        "R", (), {"stderr": "ERROR: Video unavailable", "stdout": ""})())

    with pytest.raises(RuntimeError, match="Video unavailable"):
        core.fetch_video("https://example.com/v", str(tmp_path), sub_lang="en")

    assert len(_downloads(calls)) == 1


def test_helper_distinguishes_subtitle_errors():
    assert core._subtitle_fetch_failed(SUB_429)
    assert not core._subtitle_fetch_failed("ERROR: Video unavailable")
    assert not core._subtitle_fetch_failed("")
    assert not core._subtitle_fetch_failed(None)
