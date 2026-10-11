import numpy as np

from app.models import CampaignRequirements, Segment
from app.pipeline.audio import Energy
from app.pipeline.moments import (
    Candidate,
    dedupe,
    energy_candidates,
    finalize,
    fit_length,
    length_limits,
    snap,
    windows,
)


def test_length_limits_follow_campaign_rules():
    assert length_limits(None) == (15.0, 60.0)
    assert length_limits(CampaignRequirements(min_seconds=30, max_seconds=90)) == (30.0, 90.0)
    lo, hi = length_limits(CampaignRequirements(min_seconds=70))
    assert lo == 70 and hi > lo


def test_windows_overlap_and_cover_everything():
    segs = [Segment(text=str(i), start=i * 30.0, end=i * 30.0 + 25) for i in range(60)]  # 30 minutes
    ws = windows(segs, size=600, overlap=60)
    assert ws[0][0] == 0 and ws[-1][1] >= segs[-1].end
    for (a1, b1, _), (a2, _, _) in zip(ws, ws[1:]):
        assert a2 < b1  # overlapping


def test_snap_moves_to_sentence_boundaries(transcript):
    words = transcript.words
    # Start mid-sentence, end mid-sentence.
    start, end = snap(words[6].start + 0.05, words[14].end - 0.1, words)
    starts = {w.start for w in words}
    first = min((w for w in words if w.start >= start), key=lambda w: w.start)
    assert first.start in starts
    prev = [w for w in words if w.end <= start]
    assert not prev or prev[-1].text.endswith((".", "!", "?"))
    last = max((w for w in words if w.end <= end), key=lambda w: w.end)
    assert last.text.endswith((".", "!", "?"))


def test_fit_length_trims_to_max(transcript):
    words = transcript.words
    start, end = fit_length(words[0].start, words[-1].end, words, lo=5, hi=10)
    assert end - start <= 10.01


def test_dedupe_keeps_best_of_overlapping():
    a = Candidate(10, 40, 80)
    b = Candidate(15, 45, 90)
    c = Candidate(100, 130, 50)
    kept = dedupe([a, b, c])
    assert kept == [b, c]


def test_energy_candidates_find_the_loud_part(transcript):
    db = np.full(400, -40.0, dtype=np.float32)
    db[200:220] = -5.0  # a loud burst around 100-110s
    cands = energy_candidates(Energy(db=db), transcript.words, count=2, target=30)
    assert cands and cands[0].start <= 100 <= cands[0].end
    assert cands[0].source == "energy"


def test_finalize_ranks_and_limits(transcript):
    words = transcript.words
    cands = [Candidate(words[0].start, words[20].end, 70), Candidate(words[5].start, words[25].end, 95),
             Candidate(words[30].start, words[-1].end, 60)]
    out = finalize(cands, words, None, lo=3, hi=60, max_clips=2)
    assert len(out) == 2
    assert out[0].score >= out[1].score
