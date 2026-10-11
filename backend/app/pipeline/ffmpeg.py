"""Thin wrappers around the ffmpeg / ffprobe command-line tools."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FFmpegError(
            f"{' and '.join(missing)} not found. Install ffmpeg first "
            "(Mac: `brew install ffmpeg`, Windows: `winget install Gyan.FFmpeg`)."
        )


def run(args: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip()[-2000:] or f"ffmpeg exited with {proc.returncode}")


@dataclass
class MediaInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0


def probe(path: Path) -> MediaInfo:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(f"Could not read video: {proc.stderr.strip()[-500:]}")
    data = json.loads(proc.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("The file has no video stream.")
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    width, height = int(video["width"]), int(video["height"])
    # Phone videos often store rotation as metadata; swap so we see the displayed shape.
    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = abs(int(side["rotation"]))
    rotation = rotation or abs(int(video.get("tags", {}).get("rotate", 0) or 0))
    if rotation in (90, 270):
        width, height = height, width
    num, _, den = (video.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    return MediaInfo(width=width, height=height, duration=duration, fps=fps or 30.0, has_audio=has_audio)
