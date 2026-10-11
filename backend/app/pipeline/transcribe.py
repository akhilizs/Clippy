"""Speech to text with word-level timestamps (faster-whisper, runs locally, no API cost)."""

from __future__ import annotations

import threading
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from ..models import Segment, Transcript, Word

_models: dict[str, object] = {}
_lock = threading.Lock()


def _load_model(name: str):
    from faster_whisper import WhisperModel

    with _lock:
        if name not in _models:
            try:
                import ctranslate2

                has_cuda = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                has_cuda = False
            device, compute = ("cuda", "float16") if has_cuda else ("cpu", "int8")
            _models[name] = WhisperModel(name, device=device, compute_type=compute)
        return _models[name]


def read_wav(path: Path) -> np.ndarray:
    """16 kHz mono 16-bit WAV -> float32 samples in [-1, 1].

    We decode ourselves instead of letting faster-whisper open the file, because its PyAV call
    breaks on newer PyAV releases.
    """
    with wave.open(str(path), "rb") as wf:
        if wf.getframerate() != 16000 or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("Expected 16 kHz mono 16-bit audio")
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(audio: Path, model_name: str, on_progress: Callable[[float], None] | None = None) -> Transcript:
    model = _load_model(model_name)
    segments_iter, info = model.transcribe(
        read_wav(audio),
        word_timestamps=True,
        vad_filter=True,  # skips long silences, much faster on streams
        beam_size=1,
    )
    duration = float(info.duration or 0)
    segments: list[Segment] = []
    words: list[Word] = []
    for seg in segments_iter:
        segments.append(Segment(text=seg.text.strip(), start=seg.start, end=seg.end))
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text=text, start=w.start, end=w.end))
        if on_progress and duration:
            on_progress(min(1.0, seg.end / duration))
    return Transcript(language=info.language, duration=duration, segments=segments, words=words)
