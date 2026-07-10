# Contributing

Thanks for helping improve claude-real-video.

## Reporting bugs

Open a [GitHub issue](https://github.com/HUANGCHIHHUNGLeo/claude-real-video/issues) with:

- the exact command you ran (redact private URLs if needed)
- what you expected vs. what happened, including the full error output
- your OS, Python version (`python --version`), and `crv` version (`pip show claude-real-video`)
- whether `ffmpeg -version` works in your terminal

## Suggesting features

Open an issue describing the use case first — what video, what you were trying to get out of it, and why the current flags don't cover it. Discussing before coding avoids wasted PRs.

## Pull requests

1. Fork, branch from `master`.
2. Keep the change focused — one fix or feature per PR.
3. Install and test locally:

```bash
pip install -e ".[whisper]"
crv --help                 # CLI must still work
pytest                     # run the test suite (if you have pytest installed)
```

4. Try it on at least one real video (a short local file is fine) if your change touches extraction, dedup, or transcription.
5. Describe in the PR what you changed and how you verified it.

## Response time

This project is maintained by one person. Issues and PRs are answered on a best-effort basis — usually within a few days, sometimes longer. Pinging politely after a week is fine.
