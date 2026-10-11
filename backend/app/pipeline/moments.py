"""Turn AI picks and loudness peaks into clean, ranked clip candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..models import CampaignRequirements, Segment, Word
from .audio import Energy

SENTENCE_END = (".", "?", "!", "…")
PAUSE = 0.8  # a pause this long counts as a sentence boundary


@dataclass
class Candidate:
    start: float
    end: float
    score: float
    hook: str = ""
    title: str = ""
    reason: str = ""
    source: str = "ai"  # "ai" or "energy"


def length_limits(req: CampaignRequirements | None) -> tuple[float, float]:
    """Min/max clip length in seconds: campaign rules win, otherwise a short-form friendly 15-60s."""
    lo = float(req.min_seconds) if req and req.min_seconds else 15.0
    hi = float(req.max_seconds) if req and req.max_seconds else 60.0
    if hi <= lo:
        hi = lo + 15.0
    return lo, hi


def format_lines(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments)


def windows(segments: list[Segment], size: float = 600.0, overlap: float = 60.0) -> list[tuple[float, float, list[Segment]]]:
    """Split a long transcript into overlapping chunks so moments on a boundary aren't lost."""
    if not segments:
        return []
    total = segments[-1].end
    out = []
    t = 0.0
    while t < total:
        end = t + size
        part = [s for s in segments if s.end > t and s.start < end]
        if part:
            out.append((t, min(end, total), part))
        if end >= total:
            break
        t += size - overlap
    return out


def _sentence_starts(words: list[Word]) -> set[int]:
    starts = {0}
    for i in range(1, len(words)):
        prev = words[i - 1]
        if prev.text.endswith(SENTENCE_END) or words[i].start - prev.end > PAUSE:
            starts.add(i)
    return starts


def _sentence_ends(words: list[Word]) -> set[int]:
    ends = {len(words) - 1}
    for i in range(len(words) - 1):
        if words[i].text.endswith(SENTENCE_END) or words[i + 1].start - words[i].end > PAUSE:
            ends.add(i)
    return ends


def _nearest(indices, target: float, key, tolerance: float) -> int | None:
    best, best_dist = None, tolerance
    for i in indices:
        dist = abs(key(i) - target)
        if dist <= best_dist:
            best, best_dist = i, dist
    return best


def snap(start: float, end: float, words: list[Word], tolerance: float = 3.0) -> tuple[float, float]:
    """Move the cut points to sentence boundaries so a clip never starts or ends mid-thought."""
    if not words:
        return start, end
    starts, ends = _sentence_starts(words), _sentence_ends(words)
    i = _nearest(starts, start, lambda k: words[k].start, tolerance)
    if i is None:
        i = _nearest(range(len(words)), start, lambda k: words[k].start, float("inf"))
    later_ends = [k for k in ends if k >= i]
    j = _nearest(later_ends, end, lambda k: words[k].end, tolerance)
    if j is None:
        j = _nearest(range(i, len(words)), end, lambda k: words[k].end, float("inf"))
    new_start = max(0.0, words[i].start - 0.15)
    if i > 0:
        new_start = max(new_start, words[i - 1].end)
    new_end = words[j].end + 0.3
    if j + 1 < len(words):
        new_end = min(new_end, words[j + 1].start)
    return round(new_start, 2), round(max(new_end, new_start + 0.5), 2)


def fit_length(start: float, end: float, words: list[Word], lo: float, hi: float) -> tuple[float, float]:
    """Trim or extend to the allowed length, still ending on a sentence boundary when possible."""
    if not words or lo <= end - start <= hi:
        return start, end
    ends = sorted(_sentence_ends(words))
    if end - start > hi:
        limit = start + hi
        ok = [k for k in ends if lo <= words[k].end + 0.3 - start and words[k].end + 0.3 <= limit]
        new_end = words[ok[-1]].end + 0.3 if ok else limit
    else:
        target = start + lo
        ok = [k for k in ends if words[k].end + 0.3 >= target and words[k].end + 0.3 - start <= hi]
        new_end = words[ok[0]].end + 0.3 if ok else target
    return start, round(new_end, 2)


def overlap_ratio(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shorter = min(a.end - a.start, b.end - b.start) or 1.0
    return inter / shorter


def dedupe(cands: list[Candidate], threshold: float = 0.5) -> list[Candidate]:
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: c.score, reverse=True):
        if all(overlap_ratio(c, k) < threshold for k in kept):
            kept.append(c)
    return kept


def excerpt(words: list[Word], start: float, end: float, max_words: int = 8) -> str:
    picked = [w.text for w in words if w.start >= start and w.end <= end][:max_words]
    return " ".join(picked)


def energy_candidates(energy: Energy, words: list[Word], count: int, target: float = 30.0) -> list[Candidate]:
    """No-AI fallback: clips around the loudest moments of the video."""
    if len(energy.db) == 0:
        return []
    z = energy.zscores()
    kernel = np.ones(6) / 6  # ~3 seconds
    smooth = np.convolve(z, kernel, mode="same")
    total = len(smooth) * energy.hop
    suppress = int(target / energy.hop)
    out: list[Candidate] = []
    work = smooth.copy()
    for _ in range(count):
        idx = int(np.argmax(work))
        if not np.isfinite(work[idx]) or work[idx] == -np.inf:
            break
        peak = idx * energy.hop
        start = max(0.0, min(peak - target * 0.6, total - target))
        end = min(total, start + target)
        out.append(
            Candidate(
                start=start,
                end=end,
                score=energy.score(start, end),
                hook=excerpt(words, start, end, 6),
                reason="Loudest part of the video (laughing, yelling or hype)",
                source="energy",
            )
        )
        work[max(0, idx - suppress) : idx + suppress] = -np.inf
    return out


def finalize(
    cands: list[Candidate],
    words: list[Word],
    energy: Energy | None,
    lo: float,
    hi: float,
    max_clips: int,
) -> list[Candidate]:
    cleaned: list[Candidate] = []
    for c in cands:
        if c.end <= c.start:
            continue
        start, end = snap(c.start, c.end, words)
        start, end = fit_length(start, end, words, lo, hi)
        score, hook = c.score, c.hook
        if energy is not None and c.source == "ai":
            score = 0.85 * c.score + 0.15 * energy.score(start, end)
        if c.source == "energy":  # hook = the clip's real opening words after snapping
            hook = excerpt(words, start, end, 6)
        cleaned.append(replace(c, start=start, end=end, score=round(score), hook=hook))
    return dedupe(cleaned)[:max_clips]
