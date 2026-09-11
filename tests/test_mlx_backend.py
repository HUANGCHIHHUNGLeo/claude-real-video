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


SPEECH_WAV = os.path.join(os.path.dirname(__file__), "fixtures", "speech_en.wav")


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
    """Wave the Silero pre-gate through — VAD_SPEECH, handing the engine the path it
    was given and no timestamp map — so the tests below exercise the mlx engine
    itself. A real probe needs faster-whisper, which the bare CI install does not
    have; the VAD tests opt out of this stub explicitly."""
    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: core._VadGate(core.VAD_SPEECH, wav))


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
                        lambda wav: core._VadGate(core.VAD_SILENT, duration=10.0))

    status, path = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")

    assert status == core.GATE_NO_SIGNAL and path is None
    assert called == []                                            # mlx never ran
    assert not os.path.exists(os.path.join(str(tmp_path), "transcript.txt"))


def test_unreadable_audio_is_an_error_not_a_free_pass(tmp_path, monkeypatch):
    """A file the gate could not decode is not a file mlx may transcribe ungated:
    the decode here is PyAV's, mlx loads audio through its own ffmpeg, so one
    failing says nothing about the other. Fail closed and let the chain reach
    faster-whisper, which gates itself."""
    called = []
    _install_fake_mlx(lambda a, **kw: called.append(a) or {
        "segments": [{"start": 0, "end": 1, "text": "invented"}]})

    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: core._VadGate(core.VAD_UNREADABLE))

    status, path = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ERROR and path is None
    assert called == []                                            # mlx never ran
    assert not os.path.exists(os.path.join(str(tmp_path), "transcript.txt"))


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
    gate and reaches mlx. The fixture is committed so the test does not depend on a
    TTS binary being present."""
    pytest.importorskip("faster_whisper")

    called = []
    _install_fake_mlx(lambda a, **kw: called.append(a) or {
        "segments": [{"start": 0, "end": 2.5, "text": "the quick brown fox"}]})

    from claude_real_video import core
    monkeypatch.undo()                                   # use the real _vad_speech_audio
    status, path = core._transcribe_mlx_whisper(SPEECH_WAV, str(tmp_path), "en", "turbo")

    assert status == core.GATE_ACCEPTED
    # mlx is handed the gated audio itself, not the path — the silence is gone
    assert len(called) == 1 and not isinstance(called[0], str)
    assert "quick brown fox" in open(path, encoding="utf-8").read()


def test_timestamps_restored_across_several_speech_chunks(tmp_path, monkeypatch):
    """Three speech chunks with long silences between them. mlx only ever sees the
    30s of speech, so its times must be walked back chunk by chunk — including
    across a seam, where a naive single offset would land a line in the wrong
    place — and the last one must not run off the end of the source."""
    pytest.importorskip("faster_whisper")
    import numpy as np
    from faster_whisper.vad import SpeechTimestampsMap

    from claude_real_video import core
    # speech at 10-20s, 40-50s and 80-90s of a 90s source; collapsed: 0-10, 10-20, 20-30
    chunks = [{"start": s * 16000, "end": e * 16000} for s, e in [(10, 20), (40, 50), (80, 90)]]
    monkeypatch.setattr(core, "_vad_speech_audio", lambda wav: core._VadGate(
        core.VAD_SPEECH, np.zeros(30 * 16000, dtype="float32"),
        SpeechTimestampsMap(chunks, 16000), 90.0))

    _install_fake_mlx(lambda a, **kw: {"segments": [
        {"start": 0.0, "end": 5.0, "text": "first chunk"},
        {"start": 5.0, "end": 15.0, "text": "across the seam"},   # 5 -> 15, 15 -> 45
        {"start": 25.0, "end": 31.0, "text": "past the end"},     # 31 -> 91 -> clamped
    ]})

    status, _ = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ACCEPTED

    data = json.load(open(os.path.join(str(tmp_path), "transcript.json"), encoding="utf-8"))
    segs = data["segments"] if isinstance(data, dict) else data
    assert [(s["start"], s["end"]) for s in segs] == [(10.0, 15.0), (15.0, 45.0), (85.0, 90.0)]
    assert all(0 <= s["start"] < s["end"] <= 90.0 for s in segs)


def test_restore_holds_times_inside_the_audio():
    """The bounds check on its own, with no VAD in play: negative, inverted and
    past-the-end times are corrected, and a segment with nowhere to live is
    dropped rather than written out backwards."""
    from claude_real_video.core import _restore_segment_times
    segs = _restore_segment_times([
        {"start": -3.0, "end": 2.0, "text": "starts before zero"},
        {"start": 8.0, "end": 4.0, "text": "inverted"},
        {"start": 9.5, "end": 99.0, "text": "overshoots the end"},
        {"start": 60.0, "end": 70.0, "text": "entirely past the end"},
    ], None, 10.0)
    assert [(s["start"], s["end"]) for s in segs] == [(0.0, 2.0), (8.0, 8.001), (9.5, 10.0)]
    assert all(0 <= s["start"] < s["end"] <= 10.0 for s in segs)


def test_vad_failure_is_not_a_silence_verdict(tmp_path, monkeypatch):
    """Silero/ONNX blowing up must not read as "no speech" (that would drop the
    transcript) nor as "go ahead" (that would transcribe ungated). It is a
    GATE_ERROR, so the chain moves on to a backend that gates itself."""
    pytest.importorskip("faster_whisper")
    import faster_whisper.vad as fw_vad

    from claude_real_video import core
    monkeypatch.undo()                                   # use the real _vad_speech_audio

    def boom(*a, **kw):
        raise RuntimeError("onnxruntime session failed")

    monkeypatch.setattr(fw_vad, "get_speech_timestamps", boom)

    # the file decodes fine — it is the gate that broke, and the two must not be
    # collapsed into one verdict
    assert core._vad_speech_audio(SPEECH_WAV).verdict == core.VAD_FAILED

    called = []
    _install_fake_mlx(lambda a, **kw: called.append(a) or {"segments": []})
    status, path = core._transcribe_mlx_whisper(SPEECH_WAV, str(tmp_path), "en", "turbo")
    assert status == core.GATE_ERROR and path is None
    assert called == []                                            # mlx never ran


def test_mlx_gate_error_falls_through_to_faster_whisper(tmp_path, monkeypatch):
    """End of the chain: when the mlx backend returns GATE_ERROR the gated
    faster-whisper path still runs, so a GATE_ERROR never costs a transcript."""
    from claude_real_video import core

    order = []

    def fake_mlx(wav, out_dir, lang, model):
        order.append("mlx")
        return core.GATE_ERROR, None

    def fake_fw(wav, out_dir, lang, model):
        order.append("faster-whisper")
        dst = os.path.join(out_dir, "transcript.txt")
        open(dst, "w", encoding="utf-8").write("from the CPU backend\n")
        return core.GATE_ACCEPTED, dst

    monkeypatch.setattr(core, "_have_mlx_whisper", lambda: True)
    monkeypatch.setattr(core, "_have_faster_whisper", lambda: True)
    monkeypatch.setattr(core, "_transcribe_mlx_whisper", fake_mlx)
    monkeypatch.setattr(core, "_transcribe_faster_whisper", fake_fw)
    # stand in for the ffmpeg audio extraction
    monkeypatch.setattr(core, "_run", lambda *a, **kw: open(
        os.path.join(str(tmp_path), "audio.wav"), "w").close())

    path = core._transcribe_impl("video.mp4", str(tmp_path), "en", "turbo")

    assert order == ["mlx", "faster-whisper"]
    assert path and open(path, encoding="utf-8").read().strip() == "from the CPU backend"
    assert core._last_run_no_speech is False


def test_every_segment_dropped_is_an_error_not_a_silence_verdict(tmp_path, monkeypatch):
    """mlx spoke but the bounds check threw all of it away — the timeline is broken,
    which is GATE_ERROR (try another backend), not GATE_NO_SIGNAL (terminal)."""
    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: core._VadGate(core.VAD_SPEECH, object(), None, 5.0))
    _install_fake_mlx(lambda a, **kw: {"segments": [
        {"start": 60.0, "end": 65.0, "text": "entirely past the end"}]})

    status, path = core._transcribe_mlx_whisper("audio.wav", str(tmp_path), "en", "turbo")
    assert status == core.GATE_ERROR and path is None
