from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.models import Segment, Transcript, Word

SENTENCES = [
    "Nobody talks about this.",
    "I lost everything in one night!",
    "Then my friend called me with the craziest offer.",
    "He said, you have ten seconds to decide.",
    "So I said yes.",
    "And that changed my whole life.",
    "Honestly I still can't believe it worked.",
]

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_transcript(start: float = 1.0, word_gap: float = 0.1, word_len: float = 0.3,
                    sentence_gap: float = 0.9) -> Transcript:
    """A fake transcript with realistic word timings and pauses between sentences."""
    words: list[Word] = []
    segments: list[Segment] = []
    t = start
    for sentence in SENTENCES:
        seg_start = t
        for token in sentence.split():
            words.append(Word(text=token, start=round(t, 2), end=round(t + word_len, 2)))
            t += word_len + word_gap
        segments.append(Segment(text=sentence, start=round(seg_start, 2), end=round(t - word_gap, 2)))
        t += sentence_gap
    return Transcript(language="en", duration=t, segments=segments, words=words)


@pytest.fixture
def transcript() -> Transcript:
    return make_transcript()


def make_video(path: Path, seconds: int = 30, size: str = "1280x720") -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    return make_video(tmp_path_factory.mktemp("media") / "sample.mp4")
