"""The mlx-whisper backend: same output contract as the other backends
(transcript.txt + transcript.json of {start,end,text}), GATE_* verdicts, and the
crv-model-name -> mlx-community-repo mapping. mlx_whisper is faked via sys.modules
so this runs anywhere (it is Apple-Silicon-only in reality)."""

import json
import os
import sys
import types

import pytest


def _install_fake_mlx(transcribe):
    fake = types.ModuleType("mlx_whisper")
    fake.transcribe = transcribe
    sys.modules["mlx_whisper"] = fake


@pytest.fixture(autouse=True)
def _cleanup_fake_mlx():
    yield
    sys.modules.pop("mlx_whisper", None)


def test_model_name_mapping():
    from claude_real_video.core import _MLX_MODELS
    assert _MLX_MODELS["turbo"] == "mlx-community/whisper-large-v3-turbo"
    assert _MLX_MODELS["large-v3"].startswith("mlx-community/")


def test_writes_segments_and_maps_model(tmp_path):
    seen = {}

    def transcribe(wav, path_or_hf_repo=None, language=None, condition_on_previous_text=True):
        seen["repo"] = path_or_hf_repo
        seen["language"] = language
        seen["cond"] = condition_on_previous_text
        return {"text": "x", "segments": [
            {"start": 0.0, "end": 1.2, "text": " Dzień dobry"},
            {"start": 1.2, "end": 2.0, "text": "   "},          # blank -> dropped
            {"start": 2.0, "end": 3.5, "text": "to jest test "},
        ]}

    _install_fake_mlx(transcribe)
    from claude_real_video.core import _transcribe_mlx_whisper, GATE_ACCEPTED

    status, path = _transcribe_mlx_whisper("audio.wav", str(tmp_path), "pl", "turbo")

    assert status == GATE_ACCEPTED
    assert os.path.basename(path) == "transcript.txt"
    assert seen["repo"] == "mlx-community/whisper-large-v3-turbo"  # name mapped
    assert seen["language"] == "pl"
    assert seen["cond"] is False                                   # repetition-loop guard

    txt = open(os.path.join(str(tmp_path), "transcript.txt"), encoding="utf-8").read()
    assert "Dzień dobry" in txt and "to jest test" in txt
    assert "   " not in txt.splitlines()

    data = json.load(open(os.path.join(str(tmp_path), "transcript.json"), encoding="utf-8"))
    segs = data["segments"] if isinstance(data, dict) else data
    assert len(segs) == 2                                          # blank segment dropped
    assert segs[0]["start"] == 0.0 and segs[0]["text"] == "Dzień dobry"


def test_explicit_repo_passthrough(tmp_path):
    seen = {}

    def transcribe(wav, path_or_hf_repo=None, **kw):
        seen["repo"] = path_or_hf_repo
        return {"segments": [{"start": 0, "end": 1, "text": "hi"}]}

    _install_fake_mlx(transcribe)
    from claude_real_video.core import _transcribe_mlx_whisper
    _transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "someorg/whisper-pl-mlx")
    assert seen["repo"] == "someorg/whisper-pl-mlx"               # a "/" name is passed through


def test_no_speech_is_terminal(tmp_path):
    _install_fake_mlx(lambda wav, **kw: {"segments": []})
    from claude_real_video.core import _transcribe_mlx_whisper, GATE_NO_SIGNAL
    status, path = _transcribe_mlx_whisper("audio.wav", str(tmp_path), "pl", "turbo")
    assert status == GATE_NO_SIGNAL and path is None


def test_backend_error_falls_through(tmp_path):
    def boom(wav, **kw):
        raise RuntimeError("model download failed")

    _install_fake_mlx(boom)
    from claude_real_video.core import _transcribe_mlx_whisper, GATE_ERROR
    status, path = _transcribe_mlx_whisper("audio.wav", str(tmp_path), "pl", "turbo")
    assert status == GATE_ERROR and path is None
