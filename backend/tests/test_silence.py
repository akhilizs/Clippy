from app.models import Word
from app.pipeline.silence import FPS, keep_intervals, remap_words, total_duration


def test_long_pauses_are_cut_short_ones_kept():
    words = [Word(text="a", start=1.0, end=1.3), Word(text="b", start=1.5, end=1.8),
             Word(text="c", start=4.0, end=4.4)]
    intervals = keep_intervals(words, 0.9, 5.0)
    assert len(intervals) == 2
    first, second = intervals
    assert first[0] <= 1.0 and first[1] >= 1.8 and first[1] < 4.0
    assert second[0] < 4.0 and second[1] >= 4.4


def test_intervals_are_on_frame_grid():
    words = [Word(text="x", start=1.013, end=1.377), Word(text="y", start=3.1, end=3.5)]
    for a, b in keep_intervals(words, 1.0, 4.0):
        assert abs(a * FPS - round(a * FPS)) < 1e-6
        assert abs(b * FPS - round(b * FPS)) < 1e-6


def test_no_words_keeps_whole_range():
    assert keep_intervals([], 2.0, 5.0) == [(2.0, 5.0)]


def test_remap_moves_words_onto_cut_timeline():
    words = [Word(text="a", start=1.0, end=1.3), Word(text="c", start=4.0, end=4.4)]
    intervals = [(0.9, 1.4), (3.9, 4.6)]
    out = remap_words(words, intervals)
    assert [x.text for x in out] == ["a", "c"]
    assert abs(out[0].start - 0.1) < 1e-6
    assert abs(out[1].start - (0.5 + 0.1)) < 1e-6
    assert abs(total_duration(intervals) - 1.2) < 1e-6
