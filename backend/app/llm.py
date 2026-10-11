"""The "brain": Claude picks viral moments, reads campaign rules and writes post captions.

Without an API key, OfflineBrain keeps the app usable with simple rules (loudness picks, regex rules parsing).
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from pydantic import BaseModel

from .models import CampaignRequirements

log = logging.getLogger("clippy.llm")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept `fallbacks: "default"` on the Claude API.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AIError(RuntimeError):
    """A recoverable AI failure: the pipeline falls back to loudness-based picks."""


class AIAuthError(AIError):
    """The API key is missing, wrong or out of credit. No point retrying other chunks."""


class MomentPick(BaseModel):
    start: float
    end: float
    score: int
    hook: str
    title: str
    reason: str


class MomentPicks(BaseModel):
    moments: list[MomentPick]


class PostCaption(BaseModel):
    caption: str
    hashtags: list[str]


class Brain(Protocol):
    label: str

    def find_moments(self, transcript: str, chunk_start: float, chunk_end: float, lo: float, hi: float,
                     campaign_notes: str) -> list[MomentPick]: ...

    def parse_rules(self, rules_text: str) -> CampaignRequirements: ...

    def write_caption(self, hook: str, excerpt: str, campaign_notes: str) -> PostCaption: ...


MOMENTS_SYSTEM = """\
You are a top short-form video editor. You cut long videos (podcasts, livestreams, interviews, \
reactions) into TikTok, Instagram Reels and YouTube Shorts clips for paid clipping campaigns, \
where the clipper is paid per view. Your job is to find the moments that make a stranger stop \
scrolling and watch to the very end.

What makes a great clip:
- It opens on a hook: a bold or controversial claim, a surprising fact or number, a question, \
conflict, or the start of a story that creates curiosity. Skip warm-up talk ("so, um, anyway").
- It is self-contained: someone who has never seen the source understands it without context.
- It has a payoff: a punchline, reveal, strong opinion, emotional peak, practical takeaway or \
funny reaction, and it ends right after that payoff instead of trailing off.
- High energy or high emotion: laughing, arguing, shock, hype, vulnerability.
- Quotable lines people would comment on, share or argue about.

What to avoid: moments that need earlier context, slow rambling, inside jokes, ads or sponsor \
reads, intros and outros, and anything the campaign notes forbid.

How to answer:
- The transcript lines look like "[start-end] text", times in seconds from the start of the video.
- For each moment, `start` is the start time of its first line and `end` is the end time of its \
last line. Use the transcript's times; never invent times outside the chunk you were given.
- Respect the allowed clip length you are given. Aim for 20-45 seconds when the rules allow it.
- `score` is 0-100 for viral potential: 90+ likely to blow up, 70-89 strong, 50-69 decent. Be \
strict, and leave out anything below 50. Returning zero moments is fine for a dull chunk.
- `hook` is the on-screen text shown during the first 3 seconds: at most 8 words, creates \
curiosity, honest about what happens (no fake clickbait), no hashtags or emoji.
- `title` is a short label for the clipper. `reason` is one sentence on why it will hold attention.
- Return at most 5 moments per chunk, best first."""

RULES_SYSTEM = """\
You read the rules of a paid clipping campaign (usually from Whop Content Rewards) and extract \
the requirements a clipper must follow so their clips are not rejected.
- Hashtags keep their leading '#', mentions keep their leading '@'.
- Lengths are in whole seconds. Leave a field empty or null when the rules don't say.
- platforms: use only these lowercase names: tiktok, instagram, youtube, x.
- cpm_usd: payout in USD per 1,000 views, if stated.
- banned: short phrases for anything forbidden. notes: other important rules, one short line each."""

CAPTION_SYSTEM = """\
You write the post caption (the text under the video) for a TikTok / Reels / Shorts clip in a \
paid clipping campaign. Keep it to one or two short, punchy lines that make people watch and \
comment. No more than one emoji. Put hashtags only in the `hashtags` list, each starting with '#': \
add 2-4 relevant ones. The campaign's required hashtags, mentions and credit are added \
automatically, so don't repeat them."""


def _campaign_block(notes: str) -> str:
    return f"Campaign rules to respect:\n{notes}" if notes.strip() else "No special campaign rules."


class ClaudeBrain:
    def __init__(self, api_key: str | None, model: str, client=None):
        import anthropic

        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model
        self.label = model

    def _parse(self, *, system: str, user: str, schema: type[BaseModel], effort: str, max_tokens: int):
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        if not self.model.startswith("claude-haiku-4"):
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}
        if self.model in FALLBACK_MODELS:
            # If a safety classifier declines, the API retries on Anthropic's recommended model.
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        anthropic = self._anthropic
        try:
            response = self.client.beta.messages.parse(**kwargs)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise AIAuthError("Your Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env.") from e
        except anthropic.BadRequestError as e:
            if "credit" in str(e).lower():
                raise AIAuthError("Your Anthropic account is out of credit. Add credit at console.anthropic.com.") from e
            raise AIError(f"Claude rejected the request: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Could not reach the Claude API. Is this computer online?") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude API error ({e.status_code}): {e.message}") from e
        if response.stop_reason == "refusal":
            raise AIError("Claude declined this part of the transcript.")
        if response.stop_reason == "max_tokens":
            raise AIError("Claude's answer was cut off.")
        parsed = response.parsed_output
        if parsed is None:
            raise AIError("Claude returned an answer that couldn't be read.")
        usage = response.usage
        log.info("claude %s: in=%s cached=%s out=%s", schema.__name__, usage.input_tokens,
                 getattr(usage, "cache_read_input_tokens", 0), usage.output_tokens)
        return parsed

    def find_moments(self, transcript, chunk_start, chunk_end, lo, hi, campaign_notes):
        user = (
            f"{_campaign_block(campaign_notes)}\n\n"
            f"Allowed clip length: {lo:.0f} to {hi:.0f} seconds.\n"
            f"This chunk covers {chunk_start:.0f}s to {chunk_end:.0f}s of the video.\n\n"
            f"<transcript>\n{transcript}\n</transcript>"
        )
        picks = self._parse(system=MOMENTS_SYSTEM, user=user, schema=MomentPicks, effort="high", max_tokens=16000)
        valid = []
        for m in picks.moments:
            m.start, m.end = max(m.start, chunk_start - 5), min(m.end, chunk_end + 5)
            if m.end - m.start >= 3:
                m.score = max(0, min(100, m.score))
                valid.append(m)
        return valid

    def parse_rules(self, rules_text):
        return self._parse(system=RULES_SYSTEM, user=f"<rules>\n{rules_text}\n</rules>",
                           schema=CampaignRequirements, effort="low", max_tokens=4000)

    def write_caption(self, hook, excerpt, campaign_notes):
        user = f"{_campaign_block(campaign_notes)}\n\nOn-screen hook: {hook}\n\nWhat is said in the clip:\n{excerpt}"
        return self._parse(system=CAPTION_SYSTEM, user=user, schema=PostCaption, effort="low", max_tokens=2000)


class OfflineBrain:
    """No API key: keep working with simple rules."""

    label = "offline"

    def find_moments(self, transcript, chunk_start, chunk_end, lo, hi, campaign_notes):
        return []  # the pipeline uses loudness peaks instead

    def parse_rules(self, rules_text):
        return parse_rules_offline(rules_text)

    def write_caption(self, hook, excerpt, campaign_notes):
        return PostCaption(caption=hook, hashtags=[])


_SECONDS = r"(\d{1,3})\s*(?:s\b|sec|secs|second|seconds)"


def parse_rules_offline(text: str) -> CampaignRequirements:
    lower = text.lower()
    hashtags = list(dict.fromkeys(re.findall(r"#\w+", text)))
    mentions = list(dict.fromkeys(m for m in re.findall(r"(?<![\w.])@[\w.]*\w", text)))
    min_s = max_s = None
    if m := re.search(r"(\d{1,3})\s*(?:-|–|to)\s*" + _SECONDS, lower):
        min_s, max_s = int(m.group(1)), int(m.group(2))
    if m := re.search(r"(?:min(?:imum)?|at least|longer than)\D{0,20}" + _SECONDS, lower):
        min_s = int(m.group(1))
    if m := re.search(r"(?:max(?:imum)?|at most|under|shorter than|no longer than)\D{0,20}" + _SECONDS, lower):
        max_s = int(m.group(1))
    cpm = None
    if m := re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:/|per)\s*(?:1k|1,000|1000|thousand|k)\b", lower):
        cpm = float(m.group(1))
    platforms = [p for p, keys in {
        "tiktok": ("tiktok",), "instagram": ("instagram", "reels", " ig "),
        "youtube": ("youtube", "shorts"), "x": ("twitter", " x "),
    }.items() if any(k in f" {lower} " for k in keys)]
    return CampaignRequirements(required_hashtags=hashtags, required_mentions=mentions, min_seconds=min_s,
                                max_seconds=max_s, platforms=platforms, cpm_usd=cpm)


def get_brain(api_key: str | None, model: str) -> Brain:
    if api_key:
        return ClaudeBrain(api_key, model)
    return OfflineBrain()
