"""Pluggable LLM layer for the viralsynth pipeline.

Defaults to Claude (Anthropic) when ANTHROPIC_API_KEY is set, falls back to
OpenAI when OPENAI_API_KEY is set, then to a local OpenAI-compatible endpoint
(VIRALSYNTH_LLM_BASE_URL + key), and finally to a deterministic `none` provider
that still yields usable copy so the pipeline runs fully offline.

Provider SDKs are imported lazily — you only need the one you use.
"""
from __future__ import annotations

import os
import re


class LLM:
    """Minimal chat-completion interface used by the synthesis step."""

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 600) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def available(self) -> bool:
        return True


class ClaudeLLM(LLM):
    def __init__(self, model: str = "claude-sonnet-4-0"):
        self.model = model

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 600) -> str:
        import anthropic  # lazy
        client = anthropic.Anthropic()
        msgs = [{"role": "user", "content": prompt}]
        kw = dict(model=self.model, max_tokens=max_tokens, messages=msgs)
        if system:
            kw["system"] = system
        r = client.messages.create(**kw)
        return "".join(b.text for b in r.content if getattr(b, "text", "")).strip()


class OpenAILLM(LLM):
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 600) -> str:
        from openai import OpenAI  # lazy
        client = OpenAI()
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        r = client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, messages=msgs)
        return r.choices[0].message.content.strip()


class LocalLLM(LLM):
    def __init__(self, base_url: str, model: str = "local",
                 api_key: str = "not-needed"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 600) -> str:
        import requests  # lazy
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "messages": msgs},
            timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


_CAMERA_WORDS = {
    "pan-left": "a left-to-right pan", "pan-right": "a right-to-left pan",
    "tilt-up": "an upward tilt", "tilt-down": "a downward tilt",
    "zoom-in": "a push-in", "zoom-out": "a pull-back",
    "static": "a locked-off static shot", "handheld": "a shaky handheld shot",
}


class NoneLLM(LLM):
    """Deterministic offline fallback — produces structured copy, no network."""

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 600) -> str:
        # Pull structured clues the pipeline embeds in the prompt.
        topic = _first(r"TOPIC:\s*(.+)", prompt) or "this topic"
        role = _first(r"ROLE:\s*(\w+)", prompt) or "creator"
        cam = _first(r"CAMERA:\s*([\w-]+)", prompt)
        cam_txt = _CAMERA_WORDS.get(cam, "a deliberate camera move") if cam else "deliberate camera work"
        if role == "breakdown":
            return (f"The {cam_txt} here does the heavy lifting: it keeps the eye "
                    f"on the subject instead of letting it wander. For {topic}, that "
                    f"same discipline is what makes a short feel intentional rather "
                    f"than accidental.")
        return (f"Hook them in one second, then let {cam_txt} carry the beat. "
                f"For {topic}, every cut should earn its place — pace over filler.")


def _first(pat: str, text: str) -> str | None:
    m = re.search(pat, text)
    return m.group(1).strip() if m else None


def get_llm(name: str = "auto", model: str | None = None) -> LLM:
    """Return an LLM provider. `auto` picks the first available in order:
    claude -> openai -> local -> none."""
    if name == "none":
        return NoneLLM()
    if name in ("claude", "auto"):
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                return ClaudeLLM(model or "claude-sonnet-4-0")
            except Exception:
                pass
    if name in ("openai", "auto"):
        if os.environ.get("OPENAI_API_KEY"):
            try:
                return OpenAILLM(model or "gpt-4o-mini")
            except Exception:
                pass
    if name in ("local", "auto"):
        base = os.environ.get("VIRALSYNTH_LLM_BASE_URL")
        if base:
            try:
                return LocalLLM(base, model or os.environ.get("VIRALSYNTH_LLM_MODEL", "local"),
                                os.environ.get("VIRALSYNTH_LLM_KEY", "not-needed"))
            except Exception:
                pass
    return NoneLLM()
