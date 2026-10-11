"""Renders a real clip from a synthetic video and checks the output with ffprobe."""

import subprocess

from app.config import CAPTION_FONT
from app.pipeline import ffmpeg, silence
from app.pipeline.captions import build_ass
from app.pipeline.reframe import Layout, plan_layout
from app.pipeline.render import render_clip, thumbnail

from .conftest import needs_ffmpeg


@needs_ffmpeg
def test_render_vertical_captioned_clip(tmp_path, sample_video, transcript):
    info = ffmpeg.probe(sample_video)
    assert (info.width, info.height, info.has_audio) == (1280, 720, True)
    words = transcript.words
    start, end = words[0].start - 0.1, words[20].end + 0.2
    intervals = silence.keep_intervals(words, start, end)
    assert len(intervals) > 1  # the pauses between sentences were cut
    duration = silence.total_duration(intervals)

    ass = tmp_path / "clip.ass"
    ass.write_text(build_ass(silence.remap_words(words, intervals), "Nobody talks about this", duration, CAPTION_FONT))
    layout = plan_layout(sample_video, info, start, end, finder=None)
    assert layout.mode == "blur"

    out = tmp_path / "clip.mp4"
    render_clip(sample_video, info, intervals, layout, ass, out)
    result = ffmpeg.probe(out)
    assert (result.width, result.height) == (1080, 1920)
    assert result.has_audio
    assert abs(result.duration - duration) < 0.25

    video_stream = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
         "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout
    assert abs(float(video_stream) - duration) < 0.05  # cut points line up exactly with the speech

    thumb = tmp_path / "thumb.jpg"
    thumbnail(out, thumb)
    assert thumb.stat().st_size > 1000


@needs_ffmpeg
def test_render_crop_layout(tmp_path, sample_video, transcript):
    info = ffmpeg.probe(sample_video)
    words = transcript.words[:6]
    intervals = silence.keep_intervals(words, words[0].start, words[-1].end)
    ass = tmp_path / "c.ass"
    ass.write_text(build_ass(silence.remap_words(words, intervals), "", silence.total_duration(intervals), CAPTION_FONT, 3))
    out = tmp_path / "c.mp4"
    render_clip(sample_video, info, intervals, Layout("crop", crop_x=600, crop_w=404, crop_h=720), ass, out, variant=3)
    assert (ffmpeg.probe(out).width, ffmpeg.probe(out).height) == (1080, 1920)
