"""The mlx-whisper backend: same output contract as the other backends
(transcript.txt + transcript.json of {start,end,text}), GATE_* verdicts, and the
crv-model-name -> mlx-community-repo mapping. mlx_whisper is faked via sys.modules
so this runs anywhere (it is Apple-Silicon-only in reality)."""

import json
import os
import shutil
import subprocess
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


@pytest.fixture(autouse=True)
def _stub_vad(monkeypatch):
    """Neutralise the Silero pre-gate (VAD_UNKNOWN = "could not probe", which lets
    the engine run on the original file) so the tests below exercise the mlx engine
    itself. A real probe needs faster-whisper, which the bare CI install does not
    have; the VAD-specific tests opt out of this stub explicitly."""
    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: (core.VAD_UNKNOWN, None, None))


def test_model_name_mapping():
    from claude_real_video.core import _MLX_MODELS
    assert _MLX_MODELS["turbo"] == "mlx-community/whisper-large-v3-turbo"
    assert _MLX_MODELS["large-v3"].startswith("mlx-community/")
    # "large" is one of the names crv's CLI accepts; without it the raw string
    # "large" was passed to HF as a repo id and every --whisper-model large run
    # failed over to the CPU backend.
    assert _MLX_MODELS["large"] == "mlx-community/whisper-large-v3-mlx"


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


def test_vad_pre_gate_blocks_mlx_on_silence(tmp_path, monkeypatch):
    """No speech chunks -> terminal GATE_NO_SIGNAL, and mlx is never invoked.
    mlx-whisper has no VAD of its own, so this pre-gate is the only thing standing
    between silent audio and a hallucinated caption."""
    called = []
    _install_fake_mlx(lambda wav, **kw: called.append(wav) or {
        "segments": [{"start": 0, "end": 3, "text": "I'll see you next time"}]})

    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: (core.VAD_SILENT, None, None))

    status, path = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")

    assert status == core.GATE_NO_SIGNAL and path is None
    assert called == []                                            # mlx never ran
    assert not os.path.exists(os.path.join(str(tmp_path), "transcript.txt"))


def test_vad_pre_gate_unreadable_audio_lets_mlx_try(tmp_path, monkeypatch):
    """A VAD that could not read the file returns None, not 0 — unknown is not
    evidence of silence, so the engine still gets its turn."""
    called = []
    _install_fake_mlx(lambda wav, **kw: called.append(wav) or {
        "segments": [{"start": 0, "end": 1, "text": "hi"}]})

    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: (core.VAD_UNKNOWN, None, None))

    status, _ = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ACCEPTED and called == ["audio.wav"]


def test_missing_faster_whisper_refuses_rather_than_ungated(tmp_path, monkeypatch):
    """[mlx] depends on faster-whisper for Silero. If it is somehow absent we return
    GATE_ERROR (the chain moves on) instead of transcribing without a gate."""
    called = []
    _install_fake_mlx(lambda wav, **kw: called.append(wav) or {"segments": []})

    from claude_real_video import core

    def _no_faster_whisper(wav):
        raise ImportError("No module named 'faster_whisper'")

    monkeypatch.setattr(core, "_vad_speech_audio", _no_faster_whisper)

    status, path = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ERROR and path is None
    assert called == []


def _needs_real_vad():
    pytest.importorskip("faster_whisper")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not on PATH")


def test_real_silence_is_gated_end_to_end(tmp_path, monkeypatch):
    """The genuine Silero gate on a genuinely silent file: 10s of anullsrc must not
    reach mlx. Skipped where faster-whisper/ffmpeg are unavailable (bare CI)."""
    _needs_real_vad()
    wav = str(tmp_path / "silence.wav")
    subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-f", "lavfi",
                    "-i", "anullsrc=r=16000:cl=mono", "-t", "10", wav], check=True)

    called = []
    _install_fake_mlx(lambda w, **kw: called.append(w) or {
        "segments": [{"start": 0, "end": 3, "text": "Thanks for watching!"}]})

    from claude_real_video import core
    monkeypatch.undo()                                   # use the real _vad_speech_audio
    status, path = core._transcribe_mlx_whisper(wav, str(tmp_path), "en", "turbo")

    assert status == core.GATE_NO_SIGNAL and path is None
    assert called == []


def test_real_speech_still_accepted_end_to_end(tmp_path, monkeypatch):
    """The other half of the guarantee: a file that does contain speech passes the
    gate and reaches mlx. Speech is synthesised with macOS `say`."""
    _needs_real_vad()
    if not shutil.which("say"):
        pytest.skip("no TTS available to make a speech fixture")
    aiff = str(tmp_path / "speech.aiff")
    wav = str(tmp_path / "speech.wav")
    subprocess.run(["say", "-o", aiff,
                    "The quick brown fox jumps over the lazy dog."], check=True)
    subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", aiff,
                    "-ar", "16000", "-ac", "1", wav], check=True)

    called = []
    _install_fake_mlx(lambda w, **kw: called.append(w) or {
        "segments": [{"start": 0, "end": 2.5, "text": "the quick brown fox"}]})

    from claude_real_video import core
    monkeypatch.undo()                                   # use the real _vad_speech_audio
    status, path = core._transcribe_mlx_whisper(wav, str(tmp_path), "en", "turbo")

    assert status == core.GATE_ACCEPTED
    # mlx is handed the gated audio itself, not the path — the silence is gone
    assert len(called) == 1 and not isinstance(called[0], str)
    assert "quick brown fox" in open(path, encoding="utf-8").read()


def test_gated_timestamps_are_mapped_back_to_the_original_timeline(tmp_path, monkeypatch):
    """mlx sees the collapsed speech-only audio, so its times are on that timeline;
    the written transcript must carry the original ones. Here 0-1s of speech-only
    audio corresponds to 10-11s of the source."""
    _needs_real_vad()
    import numpy as np
    from faster_whisper.vad import SpeechTimestampsMap

    from claude_real_video import core
    fake_audio = np.zeros(16000, dtype="float32")
    tsmap = SpeechTimestampsMap([{"start": 10 * 16000, "end": 20 * 16000}], 16000)
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: (core.VAD_SPEECH, fake_audio, tsmap))

    _install_fake_mlx(lambda a, **kw: {"segments": [
        {"start": 0.0, "end": 1.0, "text": "hello"}]})

    status, _ = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ACCEPTED

    data = json.load(open(os.path.join(str(tmp_path), "transcript.json"), encoding="utf-8"))
    segs = data["segments"] if isinstance(data, dict) else data
    assert segs[0]["start"] == 10.0 and segs[0]["end"] == 11.0
