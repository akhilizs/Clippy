"""Get the source video onto disk and pull out a mono 16 kHz audio track for analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import ffmpeg


def download(url: str, dest_dir: Path, on_progress: Callable[[float], None] | None = None) -> Path:
    """Download a video link (YouTube, Twitch VOD, Kick, Google Drive, direct .mp4 ...) with yt-dlp.

    Only use links the campaign gave you permission to clip.
    """
    import yt_dlp

    def hook(status: dict) -> None:
        if on_progress and status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                on_progress(min(1.0, status.get("downloaded_bytes", 0) / total))

    options = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():  # merged output gets the .mp4 extension
        candidates = sorted(dest_dir.glob("source.*"))
        if not candidates:
            raise RuntimeError("Download finished but no video file was found.")
        path = candidates[0]
    return path


def extract_audio(video: Path, out_wav: Path) -> Path:
    ffmpeg.run(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)])
    return out_wav
