"""--prompt / --prompt-file: a vocabulary hint reaches every Whisper backend,
and leaves the call unchanged when it is not given."""

import os
import subprocess
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _stub_vad(monkeypatch):
    from claude_real_video import core
    monkeypatch.setattr(core, "_vad_speech_audio",
                        lambda wav: core._VadGate(core.VAD_SPEECH, wav))


class _Seg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


def _install_fake_faster_whisper(monkeypatch, seen):
    class WhisperModel:
        def __init__(self, *a, **kw):
            pass

        def transcribe(self, wav, **kw):
            seen.update(kw)
            return iter([_Seg(0.0, 1.0, "hello")]), None

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)


def test_faster_whisper_gets_prompt_as_hotwords(tmp_path, monkeypatch):
    seen = {}
    _install_fake_faster_whisper(monkeypatch, seen)
    from claude_real_video.core import _transcribe_faster_whisper, GATE_ACCEPTED

    status, _ = _transcribe_faster_whisper("audio.wav", str(tmp_path), "zh", "turbo",
                                           prompt="self-drilling screw, gasket")
    assert status == GATE_ACCEPTED
    # hotwords ride on every 30 s window; initial_prompt would be dropped after
    # the first one because crv runs with condition_on_previous_text=False
    assert seen["hotwords"] == "self-drilling screw, gasket"
    assert "initial_prompt" not in seen
    assert seen["condition_on_previous_text"] is False


def test_faster_whisper_call_unchanged_without_prompt(tmp_path, monkeypatch):
    seen = {}
    _install_fake_faster_whisper(monkeypatch, seen)
    from claude_real_video.core import _transcribe_faster_whisper

    _transcribe_faster_whisper("audio.wav", str(tmp_path), None, "base")
    assert "hotwords" not in seen and "initial_prompt" not in seen


def test_mlx_gets_initial_prompt(tmp_path, monkeypatch):
    seen = {}

    def transcribe(wav, **kw):
        seen.update(kw)
        return {"text": "x", "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}]}

    fake = types.ModuleType("mlx_whisper")
    fake.transcribe = transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)
    from claude_real_video.core import _transcribe_mlx_whisper, GATE_ACCEPTED

    status, _ = _transcribe_mlx_whisper("audio.wav", str(tmp_path), None, "turbo",
                                        prompt="etcd, kubectl")
    assert status == GATE_ACCEPTED
    assert seen["initial_prompt"] == "etcd, kubectl"


def _install_fake_openai_whisper(monkeypatch, seen, carry_supported):
    class Model:
        def transcribe(self, wav, **kw):
            if "carry_initial_prompt" in kw and not carry_supported:
                raise TypeError("unexpected keyword argument 'carry_initial_prompt'")
            seen.clear()
            seen.update(kw)
            return {"text": "x", "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}]}

    fake = types.ModuleType("whisper")
    fake.load_model = lambda name: Model()
    monkeypatch.setitem(sys.modules, "whisper", fake)


@pytest.mark.parametrize("carry_supported", [True, False])
def test_openai_whisper_prompt(tmp_path, monkeypatch, carry_supported):
    seen = {}
    _install_fake_openai_whisper(monkeypatch, seen, carry_supported)
    from claude_real_video.core import _transcribe_whisper_package

    path = _transcribe_whisper_package("audio.wav", str(tmp_path), "en", "base",
                                       prompt="Procore, RFI")
    assert path and os.path.exists(path)
    assert seen["initial_prompt"] == "Procore, RFI"
    assert seen.get("carry_initial_prompt", False) is carry_supported


def test_cli_prompt_file_and_conflict(tmp_path):
    vocab = tmp_path / "vocab.txt"
    vocab.write_text("gasket\nheat trace\n", encoding="utf-8")
    common = [sys.executable, "-m", "claude_real_video", str(tmp_path / "missing.mp4"),
              "-o", str(tmp_path / "out")]
    both = subprocess.run(common + ["--prompt", "x", "--prompt-file", str(vocab)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert both.returncode == 2 and "not both" in both.stderr
    missing = subprocess.run(common + ["--prompt-file", str(tmp_path / "nope.txt")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert missing.returncode == 2 and "--prompt-file" in missing.stderr
