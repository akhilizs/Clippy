"""Cut, reframe, caption and encode one clip as a 1080x1920 MP4 ready for TikTok / Reels / Shorts."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config import FONTS_DIR
from . import ffmpeg
from .ffmpeg import MediaInfo
from .reframe import Layout
from .silence import FPS

OUT_W, OUT_H = 1080, 1920


def _select_expr(intervals: list[tuple[float, float]], half_frame: float = 0.0) -> str:
    # Shift by half a frame so frames on the 30 fps grid fall cleanly inside [a, b).
    return "+".join(f"gte(t,{a - half_frame:.4f})*lt(t,{b - half_frame:.4f})" for a, b in intervals)


def zoom_for(variant: int) -> float:
    """A slightly different zoom per variant so re-exports aren't byte-identical duplicates."""
    return 1.0 + 0.03 * (variant % 4)


def layout_filter(layout: Layout, info: MediaInfo, zoom: float) -> str:
    if layout.mode == "crop":
        w, h = layout.crop_w / zoom, layout.crop_h / zoom
        x = layout.crop_x + (layout.crop_w - w) / 2
        y = (layout.crop_h - h) / 2
        return (f"[vs]crop={int(w) // 2 * 2}:{int(h) // 2 * 2}:{int(x)}:{int(y)},"
                f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1[vl]")
    if layout.mode == "fill":
        return (f"[vs]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
                f"crop={OUT_W}:{OUT_H},setsar=1[vl]")
    fg_w = int(OUT_W * 1.25 * zoom) // 2 * 2  # zoom in a bit so the subject is bigger
    return (
        "[vs]split=2[bg0][fg0];"
        f"[bg0]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
        "boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.12[bg];"
        f"[fg0]scale={fg_w}:-2,crop={OUT_W}:ih[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2-80,setsar=1[vl]"
    )


def prepare_fonts(workdir: Path) -> str:
    """Copy the caption font next to the job so ffmpeg can use a simple relative path (Windows-safe)."""
    fonts = workdir / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in FONTS_DIR.glob("*.otf"):
        target = fonts / f.name
        if not target.exists():
            shutil.copy(f, target)
    return "fonts"


def render_clip(source: Path, info: MediaInfo, intervals: list[tuple[float, float]], layout: Layout,
                ass_file: Path, out: Path, variant: int = 0) -> None:
    """Render the kept intervals of `source` (absolute seconds) into `out`.

    `ass_file` and `out` must live in the same work directory; ffmpeg runs from there.
    """
    if not info.has_audio:
        raise ffmpeg.FFmpegError("The source video has no audio track.")
    workdir = ass_file.parent
    fonts = prepare_fonts(workdir)
    seek = max(0.0, intervals[0][0] - 1.0)
    rel = [(a - seek, b - seek) for a, b in intervals]
    span = rel[-1][1] + 0.5
    half = 0.5 / FPS
    graph = ";".join([
        f"[0:v]fps={FPS},select='{_select_expr(rel, half)}',setpts=N/{FPS}/TB[vs]",
        layout_filter(layout, info, zoom_for(variant)),
        f"[vl]ass={ass_file.name}:fontsdir={fonts}[vout]",
        f"[0:a]aselect='{_select_expr(rel)}',asetpts=N/SR/TB,"
        "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]",
    ])
    ffmpeg.run([
        "-ss", f"{seek:.3f}", "-t", f"{span:.3f}", "-i", str(source.resolve()),
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out.resolve()),
    ], cwd=workdir)


def thumbnail(video: Path, out: Path, at: float = 0.6) -> None:
    ffmpeg.run(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(out)])
