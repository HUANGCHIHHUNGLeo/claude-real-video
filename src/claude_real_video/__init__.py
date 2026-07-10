"""claude-real-video — let Claude (or any LLM) actually watch a video.

Scene-aware + deduplicated frame extraction plus an optional transcript,
from a URL (yt-dlp) or a local file.
"""
from .core import process, Result

try:
    from importlib.metadata import version as _v
    __version__ = _v("claude-real-video")
except Exception:  # pragma: no cover
    __version__ = "0.7.2"
__all__ = ["process", "Result", "__version__"]
