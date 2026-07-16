"""Speaker diarization (who spoke when) via sherpa-onnx — fully offline, no
account or token needed. Models are the official sherpa-onnx GitHub-release
builds: pyannote segmentation 3.0 (onnx) + a 3D-Speaker embedding extractor,
auto-downloaded to ~/.cache/claude-real-video/speaker-models/ on first use.

Install: pip install 'claude-real-video[speakers]'
"""
from __future__ import annotations
import os
import subprocess
import tarfile
import tempfile
import urllib.request

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "claude-real-video",
                         "speaker-models")

# Official sherpa-onnx release assets — plain public downloads, no token.
_SEGMENTATION_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                     "speaker-segmentation-models/"
                     "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
_SEGMENTATION_MODEL = os.path.join("sherpa-onnx-pyannote-segmentation-3-0", "model.onnx")
# note: "recongition" is the actual (typo'd) tag name in the sherpa-onnx repo
_EMBEDDING_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                  "speaker-recongition-models/"
                  "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
_EMBEDDING_MODEL = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"


def available() -> bool:
    """True when the optional [speakers] dependencies are installed."""
    import importlib.util
    return (importlib.util.find_spec("sherpa_onnx") is not None
            and importlib.util.find_spec("numpy") is not None)


def _download(url: str, dest: str, label: str) -> None:
    """Download url → dest atomically, printing coarse progress."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    print(f"  speakers: downloading {label} (first use only) ...")
    last = -1

    def hook(blocks: int, bs: int, total: int) -> None:
        nonlocal last
        if total <= 0:
            return
        pct = min(100, blocks * bs * 100 // total)
        if pct >= last + 20:
            last = pct
            print(f"  speakers:   {label}: {pct}% of {total / 1e6:.1f} MB")

    try:
        urllib.request.urlretrieve(url, part, reporthook=hook)
        os.replace(part, dest)
    except Exception as e:
        try:
            os.remove(part)
        except OSError:
            pass
        raise RuntimeError(f"could not download {label} from {url}: {e}") from e


def _ensure_models() -> tuple[str, str]:
    """Return (segmentation_model, embedding_model) paths, downloading the
    official sherpa-onnx release files into CACHE_DIR on first use."""
    seg = os.path.join(CACHE_DIR, _SEGMENTATION_MODEL)
    if not os.path.exists(seg):
        tar_path = os.path.join(CACHE_DIR, "segmentation.tar.bz2")
        _download(_SEGMENTATION_URL, tar_path, "segmentation model")
        with tarfile.open(tar_path, "r:bz2") as tf:
            try:
                tf.extractall(CACHE_DIR, filter="data")
            except TypeError:  # Python < 3.12 has no `filter` kwarg
                tf.extractall(CACHE_DIR)
        os.remove(tar_path)
        if not os.path.exists(seg):
            raise RuntimeError(f"segmentation archive did not contain {_SEGMENTATION_MODEL}")
    emb = os.path.join(CACHE_DIR, _EMBEDDING_MODEL)
    if not os.path.exists(emb):
        _download(_EMBEDDING_URL, emb, "speaker embedding model")
    return seg, emb


def _load_samples(audio_path: str) -> "tuple":
    """Any audio/video file → (float32 mono samples, 16000) via ffmpeg."""
    import numpy as np
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav = tf.name
    try:
        r = subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-vn",
                            "-ar", "16000", "-ac", "1", wav,
                            "-hide_banner", "-loglevel", "error"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.getsize(wav):
            raise RuntimeError(f"ffmpeg could not decode audio from {audio_path}")
        import wave
        with wave.open(wav) as w:
            raw = w.readframes(w.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return samples, 16000
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


def diarize(audio_path: str, num_speakers: int = -1,
            cluster_threshold: float = 0.9) -> list[dict]:
    """Who spoke when. Returns [{start, end, speaker}] with speaker labels like
    "SPEAKER_00" (numbered by first appearance), sorted by start time.
    `audio_path` can be any file ffmpeg can decode (the extracted source.mp4
    works directly). Leave num_speakers at -1 to auto-detect; a smaller
    cluster_threshold finds more speakers (0.9 calibrated on the official
    sherpa-onnx 4-speaker sample — the upstream example's 0.5 over-splits
    with this eres2net embedding model)."""
    if not available():
        raise RuntimeError(
            "speaker diarization needs the optional dependencies — "
            "install them with: pip install 'claude-real-video[speakers]'")
    import sherpa_onnx

    seg_model, emb_model = _ensure_models()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=seg_model)),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=emb_model),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers, threshold=cluster_threshold),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("speaker diarization config invalid — try deleting "
                           f"{CACHE_DIR} to force a re-download of the models")
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    samples, rate = _load_samples(audio_path)
    if rate != sd.sample_rate:  # both are 16 kHz today; guard against upstream changes
        raise RuntimeError(f"model expects {sd.sample_rate} Hz audio, got {rate}")

    last = -1

    def progress(done: int, total: int) -> int:
        nonlocal last
        pct = done * 100 // max(1, total)
        if pct >= last + 25:
            last = pct
            print(f"  speakers: diarizing ... {pct}%")
        return 0

    result = sd.process(samples, callback=progress).sort_by_start_time()
    # renumber by first appearance so labels are contiguous (SPEAKER_00, 01, ...)
    order: dict[int, int] = {}
    turns = []
    for r in result:
        idx = order.setdefault(r.speaker, len(order))
        turns.append({"start": round(r.start, 2), "end": round(r.end, 2),
                      "speaker": f"SPEAKER_{idx:02d}"})
    return turns


def assign_speakers(segments: list[dict], turns: list[dict]) -> list[dict]:
    """Label transcript segments with speakers: for each transcript segment the
    speaker whose diarization turns overlap it the most wins; a segment no turn
    touches falls back to the nearest turn within 2 s, else stays unlabelled.
    Mutates and returns `segments` (adds a "speaker" key)."""
    for seg in segments:
        s, e = float(seg.get("start", 0)), float(seg.get("end", 0))
        overlap: dict[str, float] = {}
        for t in turns:
            ov = min(e, t["end"]) - max(s, t["start"])
            if ov > 0:
                overlap[t["speaker"]] = overlap.get(t["speaker"], 0.0) + ov
        if overlap:
            seg["speaker"] = max(overlap, key=lambda k: overlap[k])
        else:
            near = min(turns, key=lambda t: max(t["start"] - e, s - t["end"], 0.0),
                       default=None)
            if near is not None and max(near["start"] - e, s - near["end"], 0.0) <= 2.0:
                seg["speaker"] = near["speaker"]
    return segments
