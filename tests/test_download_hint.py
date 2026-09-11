"""0.10.4: a failed URL download must name the installed yt-dlp and the upgrade command."""
import claude_real_video.core as core


def test_upgrade_hint_mentions_version_and_command(monkeypatch):
    monkeypatch.setattr(core, "_have", lambda tool: True)
    class R:  # minimal CompletedProcess stand-in
        stdout = "2026.07.04\n"
        stderr = ""
    monkeypatch.setattr(core, "_run", lambda cmd: R())
    hint = core._ytdlp_upgrade_hint()
    assert "2026.07.04" in hint
    assert "pip install -U 'yt-dlp[default,deno]'" in hint


def test_hint_survives_missing_ytdlp(monkeypatch):
    monkeypatch.setattr(core, "_have", lambda tool: False)
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name == "yt_dlp":
            raise ImportError
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    hint = core._ytdlp_upgrade_hint()
    assert "unknown" in hint and "pip install -U" in hint
