"""Dead-air removal: keep only the spoken parts of a clip (jump cuts)."""

from __future__ import annotations

from ..models import Word

FPS = 30


def _grid(t: float) -> float:
    """Snap to the 30 fps frame grid so audio and video cut lengths match exactly."""
    return round(t * FPS) / FPS


def keep_intervals(words: list[Word], start: float, end: float, max_gap: float = 0.45,
                   pad: float = 0.1) -> list[tuple[float, float]]:
    """Speech intervals inside [start, end]; silences longer than max_gap are cut out."""
    inside = [w for w in words if w.end > start and w.start < end]
    if not inside:
        return [(_grid(start), _grid(end))]
    intervals: list[list[float]] = []
    for w in inside:
        s, e = max(start, w.start - pad), min(end, w.end + pad)
        if intervals and s - intervals[-1][1] <= max_gap:
            intervals[-1][1] = max(intervals[-1][1], e)
        else:
            intervals.append([s, e])
    # Let the last word ring out a little instead of cutting hard.
    intervals[-1][1] = min(end, intervals[-1][1] + 0.2)
    out = []
    for s, e in intervals:
        s, e = _grid(s), _grid(e)
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        elif e - s >= 2 / FPS:
            out.append((s, e))
    return out or [(_grid(start), _grid(end))]


def total_duration(intervals: list[tuple[float, float]]) -> float:
    return sum(e - s for s, e in intervals)


def remap_words(words: list[Word], intervals: list[tuple[float, float]]) -> list[Word]:
    """Move word timings onto the cut clip's timeline (0 = first kept frame)."""
    out: list[Word] = []
    offset = 0.0
    for s, e in intervals:
        for w in words:
            if w.end > s and w.start < e:
                ws, we = max(w.start, s), min(w.end, e)
                out.append(Word(text=w.text, start=round(ws - s + offset, 3), end=round(we - s + offset, 3)))
        offset += e - s
    return out
