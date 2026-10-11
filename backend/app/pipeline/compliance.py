"""Build the post caption and check a clip against the campaign rules before posting."""

from __future__ import annotations

import re

from ..models import CampaignRequirements, Issue


def _norm_tag(tag: str, prefix: str) -> str:
    tag = tag.strip()
    return tag if tag.startswith(prefix) else prefix + tag


def _contains(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text, re.IGNORECASE) is not None


def build_post_caption(text: str, suggested_tags: list[str], req: CampaignRequirements | None) -> str:
    req = req or CampaignRequirements()
    lines = [text.strip()]
    if req.credit_text and req.credit_text.lower() not in text.lower():
        lines.append(req.credit_text.strip())
    mentions = [_norm_tag(m, "@") for m in req.required_mentions]
    tags: list[str] = []
    for t in [*req.required_hashtags, *suggested_tags]:
        t = _norm_tag(t.replace(" ", ""), "#")
        if len(t) > 1 and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    extras = [m for m in mentions if not _contains(text, m)] + [t for t in tags if not _contains(text, t)]
    if extras:
        lines.append(" ".join(extras))
    return "\n".join(line for line in lines if line)


def check(req: CampaignRequirements | None, duration: float | None, caption: str) -> list[Issue]:
    if req is None:
        return []
    issues: list[Issue] = []
    for tag in req.required_hashtags:
        tag = _norm_tag(tag, "#")
        if not _contains(caption, tag):
            issues.append(Issue(level="error", message=f"Caption is missing required hashtag {tag}"))
    for mention in req.required_mentions:
        mention = _norm_tag(mention, "@")
        if not _contains(caption, mention):
            issues.append(Issue(level="error", message=f"Caption is missing required mention {mention}"))
    if req.credit_text and req.credit_text.lower() not in caption.lower():
        issues.append(Issue(level="error", message=f"Caption is missing the credit: {req.credit_text}"))
    if duration is not None:
        if req.min_seconds and duration < req.min_seconds:
            issues.append(Issue(level="error", message=f"Clip is {duration:.0f}s; campaign minimum is {req.min_seconds}s"))
        if req.max_seconds and duration > req.max_seconds:
            issues.append(Issue(level="error", message=f"Clip is {duration:.0f}s; campaign maximum is {req.max_seconds}s"))
    if req.platforms:
        issues.append(Issue(level="info", message="Allowed platforms: " + ", ".join(req.platforms)))
    for rule in req.banned:
        issues.append(Issue(level="warning", message=f"Not allowed: {rule}"))
    for note in req.notes:
        issues.append(Issue(level="info", message=note))
    return issues
