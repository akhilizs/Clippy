"""The Claude calls are tested against a fake client, so no network or API key is needed."""

from types import SimpleNamespace

import pytest

from app.llm import FALLBACK_BETA, AIError, ClaudeBrain, MomentPick, MomentPicks, OfflineBrain, parse_rules_offline


class FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed, self.stop_reason, self.calls = parsed, stop_reason, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=self.parsed, usage=usage)


def brain_with(parsed, stop_reason="end_turn", model="claude-opus-5-5"):
    messages = FakeMessages(parsed, stop_reason)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeBrain(api_key="test", model=model, client=client), messages


def test_find_moments_request_shape_and_clamping():
    picks = MomentPicks(moments=[
        MomentPick(start=100, end=130, score=120, hook="h", title="t", reason="r"),
        MomentPick(start=50, end=51, score=80, hook="h", title="t", reason="too short"),
    ])
    brain, messages = brain_with(picks)
    out = brain.find_moments("[100.0-130.0] hi", 90, 600, 15, 60, "Use #ad")
    assert len(out) == 1 and out[0].score == 100
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "high"}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_format"] is MomentPicks
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Use #ad" in call["messages"][0]["content"]


def test_refusal_becomes_ai_error():
    brain, _ = brain_with(None, stop_reason="refusal")
    with pytest.raises(AIError):
        brain.find_moments("x", 0, 10, 15, 60, "")


def test_haiku_gets_no_fallbacks():
    brain, messages = brain_with(MomentPicks(moments=[]), model="claude-haiku-5-5")
    brain.find_moments("x", 0, 10, 15, 60, "")
    assert "fallbacks" not in messages.calls[0]


def test_offline_rules_parser():
    rules = """Post on TikTok and Instagram Reels. Clips must be 15-60 seconds.
    Use #ad and #MrClips and tag @mrclips in the caption. We pay $1.50 per 1k views. No reuploads."""
    req = parse_rules_offline(rules)
    assert req.required_hashtags == ["#ad", "#MrClips"]
    assert req.required_mentions == ["@mrclips"]
    assert (req.min_seconds, req.max_seconds) == (15, 60)
    assert req.cpm_usd == 1.5
    assert set(req.platforms) == {"tiktok", "instagram"}


def test_offline_brain_picks_nothing_so_loudness_takes_over():
    assert OfflineBrain().find_moments("x", 0, 10, 15, 60, "") == []
