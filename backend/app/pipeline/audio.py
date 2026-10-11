"""Loudness over time. Loud spikes (laughing, yelling, hype) are a cheap signal for good moments."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HOP_SECONDS = 0.5


@dataclass
class Energy:
    """Loudness in dB, one value per HOP_SECONDS."""

    db: np.ndarray
    hop: float = HOP_SECONDS

    def window(self, start: float, end: float) -> np.ndarray:
        a, b = int(start / self.hop), max(int(start / self.hop) + 1, int(end / self.hop))
        return self.db[a:b]

    def zscores(self) -> np.ndarray:
        if len(self.db) == 0:
            return self.db
        std = float(self.db.std()) or 1.0
        return (self.db - float(self.db.mean())) / std

    def score(self, start: float, end: float) -> float:
        """0-100: how much louder/more intense this range is than the video overall."""
        z = self.zscores()
        a, b = int(start / self.hop), max(int(start / self.hop) + 1, int(end / self.hop))
        part = z[a:b]
        if len(part) == 0:
            return 0.0
        top = np.sort(part)[-max(1, len(part) // 5):]  # loudest 20% of the range
        return float(np.clip(50 + 25 * top.mean(), 0, 100))


def loudness(wav_path: Path, hop: float = HOP_SECONDS) -> Energy:
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        width = wf.getsampwidth()
        channels = wf.getnchannels()
        frames_per_hop = int(rate * hop)
        values: list[float] = []
        while True:
            raw = wf.readframes(frames_per_hop)
            if not raw:
                break
            dtype = np.int16 if width == 2 else np.int32
            samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)
            full_scale = float(np.iinfo(dtype).max)
            rms = np.sqrt(np.mean(np.square(samples / full_scale))) if len(samples) else 0.0
            values.append(20 * np.log10(max(rms, 1e-5)))
    return Energy(db=np.array(values, dtype=np.float32), hop=hop)
