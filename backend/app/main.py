"""HTTP API the iPhone app talks to."""

from __future__ import annotations

import logging
import re
import secrets
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from . import __version__
from .config import Settings, get_settings
from .llm import AIError
from .models import (
    Campaign,
    CampaignIn,
    CampaignUpdate,
    Clip,
    ClipUpdate,
    Job,
    JobIn,
    JobWithClips,
    Submission,
    SubmissionIn,
    SubmissionUpdate,
    ViewSnapshot,
)
from .pipeline.compliance import check
from .store import Store
from .worker import Pipeline, clip_paths

log = logging.getLogger("clippy.api")


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = pipeline.store if pipeline else Store(settings.data_dir)
    pipeline = pipeline or Pipeline(store, settings)
    app = FastAPI(title="Clippy backend", version=__version__)
    app.state.pipeline = pipeline

    def auth(request: Request) -> None:
        token = request.headers.get("x-clippy-token") or request.query_params.get("token") or ""
        if not secrets.compare_digest(token.upper(), settings.access_token.upper()):
            raise HTTPException(401, "Wrong or missing access code. Copy it from the backend window.")

    def get_or_404(table: str, obj_id: str):
        obj = store.get(table, obj_id)
        if obj is None:
            raise HTTPException(404, f"{table[:-1].capitalize()} not found")
        return obj

    def with_clips(job: Job) -> JobWithClips:
        return JobWithClips(**job.model_dump(), clips=store.clips_for_job(job.id))

    def earnings(sub: Submission) -> Submission:
        campaign = store.get("campaigns", sub.campaign_id) if sub.campaign_id else None
        cpm = campaign.requirements.cpm_usd if campaign else None
        sub.estimated_earnings_usd = round(sub.views / 1000 * cpm, 2) if cpm else None
        return sub

    # ------------------------------------------------------------ status

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "ai": pipeline.brain.label,
                "whisper_model": settings.whisper_model}

    @app.get("/auth/check", dependencies=[Depends(auth)])
    def auth_check():
        return {"ok": True}

    # ------------------------------------------------------------ campaigns

    @app.post("/campaigns", dependencies=[Depends(auth)])
    def create_campaign(body: CampaignIn) -> Campaign:
        campaign = Campaign(name=body.name.strip() or "Untitled campaign", rules_text=body.rules_text,
                            source_url=body.source_url)
        if body.rules_text.strip():
            campaign.requirements = _parse_rules(body.rules_text)
        if body.cpm_usd is not None:
            campaign.requirements.cpm_usd = body.cpm_usd
        store.put("campaigns", campaign)
        return campaign

    def _parse_rules(text: str):
        try:
            return pipeline.brain.parse_rules(text)
        except AIError as e:
            log.warning("AI rules parsing failed, using simple parser: %s", e)
            from .llm import parse_rules_offline

            return parse_rules_offline(text)

    @app.get("/campaigns", dependencies=[Depends(auth)])
    def list_campaigns() -> list[Campaign]:
        return store.list("campaigns")

    @app.get("/campaigns/{campaign_id}", dependencies=[Depends(auth)])
    def get_campaign(campaign_id: str) -> Campaign:
        return get_or_404("campaigns", campaign_id)

    @app.put("/campaigns/{campaign_id}", dependencies=[Depends(auth)])
    def update_campaign(campaign_id: str, body: CampaignUpdate) -> Campaign:
        campaign: Campaign = get_or_404("campaigns", campaign_id)
        if body.name is not None:
            campaign.name = body.name
        if body.source_url is not None:
            campaign.source_url = body.source_url
        if body.requirements is not None:
            campaign.requirements = body.requirements
        if body.rules_text is not None:
            changed = body.rules_text != campaign.rules_text
            campaign.rules_text = body.rules_text
            if (changed or body.reparse) and body.rules_text.strip():
                cpm = campaign.requirements.cpm_usd
                campaign.requirements = _parse_rules(body.rules_text)
                campaign.requirements.cpm_usd = campaign.requirements.cpm_usd or cpm
        store.put("campaigns", campaign)
        return campaign

    @app.delete("/campaigns/{campaign_id}", dependencies=[Depends(auth)])
    def delete_campaign(campaign_id: str):
        store.delete("campaigns", campaign_id)
        return {"ok": True}

    # ------------------------------------------------------------ jobs

    @app.post("/jobs", dependencies=[Depends(auth)])
    def create_job(body: JobIn) -> JobWithClips:
        url = body.source_url.strip()
        if not re.match(r"^https?://", url):
            raise HTTPException(400, "Paste a full link starting with http:// or https://")
        job = Job(source_url=url, campaign_id=body.campaign_id or None, source_name=url)
        store.put("jobs", job)
        pipeline.submit_job(job.id)
        return with_clips(job)

    @app.post("/jobs/upload", dependencies=[Depends(auth)])
    async def upload_job(request: Request, filename: str = "video.mp4", campaign_id: str | None = None) -> JobWithClips:
        """Raw request body = the video file (so the phone can stream it straight from disk)."""
        suffix = Path(filename).suffix.lower() or ".mp4"
        if not re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
            suffix = ".mp4"
        job = Job(campaign_id=campaign_id or None, source_name=Path(filename).name)
        jd = store.job_dir(job.id)
        part = jd / f"source{suffix}.part"
        size = 0
        with part.open("wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                size += len(chunk)
        if size == 0:
            shutil.rmtree(jd, ignore_errors=True)
            raise HTTPException(400, "The upload was empty.")
        part.rename(jd / f"source{suffix}")
        store.put("jobs", job)
        pipeline.submit_job(job.id)
        return with_clips(job)

    @app.get("/jobs", dependencies=[Depends(auth)])
    def list_jobs() -> list[JobWithClips]:
        return [with_clips(j) for j in store.list("jobs")]

    @app.get("/jobs/{job_id}", dependencies=[Depends(auth)])
    def get_job(job_id: str) -> JobWithClips:
        return with_clips(get_or_404("jobs", job_id))

    @app.post("/jobs/{job_id}/retry", dependencies=[Depends(auth)])
    def retry_job(job_id: str) -> JobWithClips:
        job: Job = get_or_404("jobs", job_id)
        job.status, job.error, job.progress, job.message = "queued", None, 0.0, "Waiting to start"
        store.put("jobs", job)
        pipeline.submit_job(job.id)
        return with_clips(job)

    @app.delete("/jobs/{job_id}", dependencies=[Depends(auth)])
    def delete_job(job_id: str):
        for clip in store.clips_for_job(job_id):
            store.delete("clips", clip.id)
        store.delete("jobs", job_id)
        shutil.rmtree(store.jobs_dir / job_id, ignore_errors=True)
        return {"ok": True}

    # ------------------------------------------------------------ clips

    @app.get("/clips/{clip_id}", dependencies=[Depends(auth)])
    def get_clip(clip_id: str) -> Clip:
        return get_or_404("clips", clip_id)

    @app.patch("/clips/{clip_id}", dependencies=[Depends(auth)])
    def update_clip(clip_id: str, body: ClipUpdate) -> Clip:
        clip: Clip = get_or_404("clips", clip_id)
        visual_change = False
        if body.hook is not None and body.hook != clip.hook:
            clip.hook, visual_change = body.hook, True
        if body.start is not None or body.end is not None:
            start = body.start if body.start is not None else clip.start
            end = body.end if body.end is not None else clip.end
            if end - start < 3:
                raise HTTPException(400, "A clip must be at least 3 seconds long.")
            clip.start, clip.end, visual_change = max(0.0, start), end, True
        if body.review is not None:
            clip.review = body.review
        if body.post_caption is not None:
            clip.post_caption = body.post_caption
            job = store.get("jobs", clip.job_id)
            campaign = store.get("campaigns", job.campaign_id) if job and job.campaign_id else None
            clip.issues = check(campaign.requirements if campaign else None, clip.duration, clip.post_caption)
        if body.new_variant:
            clip.variant, visual_change = clip.variant + 1, True
        store.put("clips", clip)
        if body.rerender or visual_change:
            pipeline.submit_render(clip.id)
            clip = store.get("clips", clip.id)
        return clip

    @app.post("/clips/{clip_id}/caption", dependencies=[Depends(auth)])
    def regenerate_caption(clip_id: str) -> Clip:
        return pipeline.regenerate_caption(get_or_404("clips", clip_id))

    @app.get("/clips/{clip_id}/video", dependencies=[Depends(auth)])
    def clip_video(clip_id: str):
        path = clip_paths(store, get_or_404("clips", clip_id))["video"]
        if not path.exists():
            raise HTTPException(404, "This clip hasn't been rendered yet.")
        return FileResponse(path, media_type="video/mp4", filename=f"clippy-{clip_id}.mp4",
                            content_disposition_type="inline")

    @app.get("/clips/{clip_id}/thumbnail", dependencies=[Depends(auth)])
    def clip_thumbnail(clip_id: str):
        path = clip_paths(store, get_or_404("clips", clip_id))["thumb"]
        if not path.exists():
            raise HTTPException(404, "No thumbnail yet.")
        return FileResponse(path, media_type="image/jpeg")

    # ------------------------------------------------------------ submissions

    @app.post("/submissions", dependencies=[Depends(auth)])
    def create_submission(body: SubmissionIn) -> Submission:
        campaign_id = body.campaign_id
        if campaign_id is None and body.clip_id:
            clip = store.get("clips", body.clip_id)
            job = store.get("jobs", clip.job_id) if clip else None
            campaign_id = job.campaign_id if job else None
        sub = Submission(clip_id=body.clip_id, campaign_id=campaign_id, platform=body.platform,
                         url=body.url.strip(), views=body.views)
        if body.views:
            sub.snapshots.append(ViewSnapshot(views=body.views))
        sub = earnings(sub)
        store.put("submissions", sub)
        return sub

    @app.get("/submissions", dependencies=[Depends(auth)])
    def list_submissions() -> list[Submission]:
        return [earnings(s) for s in store.list("submissions")]

    @app.patch("/submissions/{submission_id}", dependencies=[Depends(auth)])
    def update_submission(submission_id: str, body: SubmissionUpdate) -> Submission:
        sub: Submission = get_or_404("submissions", submission_id)
        if body.url is not None:
            sub.url = body.url.strip()
        if body.platform is not None:
            sub.platform = body.platform
        if body.views is not None and body.views != sub.views:
            sub.views = body.views
            sub.snapshots.append(ViewSnapshot(views=body.views))
        sub = earnings(sub)
        store.put("submissions", sub)
        return sub

    @app.delete("/submissions/{submission_id}", dependencies=[Depends(auth)])
    def delete_submission(submission_id: str):
        store.delete("submissions", submission_id)
        return {"ok": True}

    return app
