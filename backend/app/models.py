"""Data models shared by the API, the store and the pipeline."""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


# ---------------------------------------------------------------- transcript


class Word(BaseModel):
    text: str
    start: float
    end: float


class Segment(BaseModel):
    text: str
    start: float
    end: float


class Transcript(BaseModel):
    language: str | None = None
    duration: float = 0.0
    segments: list[Segment] = []
    words: list[Word] = []


# ---------------------------------------------------------------- campaigns


class CampaignRequirements(BaseModel):
    """What a Whop campaign's rules ask for. Extracted by the AI from pasted rules text."""

    required_hashtags: list[str] = []
    required_mentions: list[str] = []
    credit_text: str | None = Field(None, description="Credit line the post caption must contain, if any")
    min_seconds: int | None = None
    max_seconds: int | None = None
    platforms: list[str] = Field([], description="Allowed platforms, e.g. tiktok, instagram, youtube, x")
    banned: list[str] = Field([], description="Things the rules forbid, e.g. 'no reuploads', 'no AI voice'")
    notes: list[str] = Field([], description="Other important rules, one short line each")
    cpm_usd: float | None = Field(None, description="Payout in USD per 1,000 views")


class CampaignIn(BaseModel):
    name: str
    rules_text: str = ""
    source_url: str | None = None
    cpm_usd: float | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    rules_text: str | None = None
    source_url: str | None = None
    requirements: CampaignRequirements | None = None
    reparse: bool = False


class Campaign(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    rules_text: str = ""
    source_url: str | None = None
    requirements: CampaignRequirements = CampaignRequirements()
    created_at: float = Field(default_factory=now)


# ---------------------------------------------------------------- jobs & clips

JobStatus = Literal["queued", "downloading", "transcribing", "finding", "rendering", "done", "failed"]
RenderStatus = Literal["pending", "rendering", "ready", "failed"]
Review = Literal["new", "kept", "discarded"]


class Issue(BaseModel):
    level: Literal["error", "warning", "info"]
    message: str


class Clip(BaseModel):
    id: str = Field(default_factory=new_id)
    job_id: str
    rank: int = 0
    start: float
    end: float
    score: int = 0
    hook: str = ""
    title: str = ""
    reason: str = ""
    render_status: RenderStatus = "pending"
    review: Review = "new"
    duration: float | None = None
    variant: int = 0
    layout: str | None = None
    post_caption: str = ""
    issues: list[Issue] = []
    error: str | None = None
    updated_at: float = Field(default_factory=now)


class JobIn(BaseModel):
    source_url: str
    campaign_id: str | None = None


class Job(BaseModel):
    id: str = Field(default_factory=new_id)
    campaign_id: str | None = None
    source_url: str | None = None
    source_name: str = ""
    status: JobStatus = "queued"
    progress: float = 0.0
    message: str = "Waiting to start"
    error: str | None = None
    source_duration: float | None = None
    created_at: float = Field(default_factory=now)


class JobWithClips(Job):
    clips: list[Clip] = []


class ClipUpdate(BaseModel):
    hook: str | None = None
    start: float | None = None
    end: float | None = None
    review: Review | None = None
    post_caption: str | None = None
    rerender: bool = False
    new_variant: bool = False


# ---------------------------------------------------------------- submissions


class ViewSnapshot(BaseModel):
    at: float = Field(default_factory=now)
    views: int


class SubmissionIn(BaseModel):
    clip_id: str | None = None
    campaign_id: str | None = None
    platform: str
    url: str
    views: int = 0


class SubmissionUpdate(BaseModel):
    url: str | None = None
    platform: str | None = None
    views: int | None = None


class Submission(BaseModel):
    id: str = Field(default_factory=new_id)
    clip_id: str | None = None
    campaign_id: str | None = None
    platform: str
    url: str
    views: int = 0
    snapshots: list[ViewSnapshot] = []
    estimated_earnings_usd: float | None = None
    created_at: float = Field(default_factory=now)
