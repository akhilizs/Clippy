"""Runs the clipping pipeline in the background: source -> transcript -> moments -> rendered clips."""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .config import CAPTION_FONT, Settings
from .llm import AIAuthError, AIError, Brain, PostCaption, get_brain
from .models import Campaign, Clip, Job, Transcript, now
from .pipeline import audio, ffmpeg, ingest, moments, silence
from .pipeline.captions import build_ass
from .pipeline.compliance import build_post_caption, check
from .pipeline.reframe import FaceFinder, plan_layout
from .pipeline.render import render_clip, thumbnail
from .store import Store

log = logging.getLogger("clippy.worker")

Transcriber = Callable[[Path, Callable[[float], None]], Transcript]


def campaign_notes(campaign: Campaign | None) -> str:
    if campaign is None:
        return ""
    parts = []
    if campaign.rules_text.strip():
        parts.append(campaign.rules_text.strip()[:4000])
    req = campaign.requirements
    parts += [f"Not allowed: {b}" for b in req.banned] + req.notes
    return "\n".join(parts)


class Pipeline:
    def __init__(self, store: Store, settings: Settings, brain: Brain | None = None,
                 transcriber: Transcriber | None = None, face_finder: FaceFinder | None | bool = None):
        self.store = store
        self.settings = settings
        self.brain = brain or get_brain(settings.anthropic_api_key, settings.claude_model)
        if transcriber is None:
            from .pipeline import transcribe as tr

            transcriber = lambda wav, cb: tr.transcribe(wav, settings.whisper_model, cb)  # noqa: E731
        self.transcriber = transcriber
        self._finder = face_finder  # None = create lazily, False = never detect faces
        # One job at a time: transcription and rendering already use all CPU cores.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clippy")
        self._recover()

    # ------------------------------------------------------------------ helpers

    def _recover(self) -> None:
        """Anything that was running when the backend stopped can't still be running."""
        for job in self.store.list("jobs"):
            if job.status not in ("done", "failed"):
                job.status, job.error, job.message = "failed", "The backend was restarted.", "Interrupted - tap Retry"
                self.store.put("jobs", job)
            for clip in self.store.clips_for_job(job.id):
                if clip.render_status in ("pending", "rendering"):
                    clip.render_status, clip.error = "failed", "The backend was restarted."
                    self.store.put("clips", clip)

    def finder(self) -> FaceFinder | None:
        if self._finder is None:
            self._finder = FaceFinder(self.settings.data_dir / "models")
        return self._finder or None

    def _save(self, job: Job, **fields) -> None:
        for key, value in fields.items():
            setattr(job, key, value)
        self.store.put("jobs", job)

    def source_path(self, job_id: str) -> Path | None:
        found = [p for p in self.store.job_dir(job_id).glob("source.*") if not p.name.endswith(".part")]
        return found[0] if found else None

    def load_transcript(self, job_id: str) -> Transcript | None:
        path = self.store.job_dir(job_id) / "transcript.json"
        return Transcript.model_validate_json(path.read_text()) if path.exists() else None

    def campaign_for(self, job: Job) -> Campaign | None:
        return self.store.get("campaigns", job.campaign_id) if job.campaign_id else None

    # ------------------------------------------------------------------ public

    def submit_job(self, job_id: str) -> Future:
        return self.executor.submit(self.run_job, job_id)

    def submit_render(self, clip_id: str) -> Future:
        clip = self.store.get("clips", clip_id)
        if clip:
            clip.render_status, clip.error = "pending", None
            self.store.put("clips", clip)
        return self.executor.submit(self.render_by_id, clip_id)

    def run_job(self, job_id: str) -> None:
        job = self.store.get("jobs", job_id)
        if job is None:
            return
        try:
            self._run(job)
        except Exception as e:  # report every failure to the phone instead of dying silently
            log.exception("Job %s failed", job_id)
            self._save(job, status="failed", error=str(e) or e.__class__.__name__, message="Failed")

    def render_by_id(self, clip_id: str) -> None:
        clip = self.store.get("clips", clip_id)
        job = self.store.get("jobs", clip.job_id) if clip else None
        if clip is None or job is None:
            return
        self.render(clip, job)

    def regenerate_caption(self, clip: Clip) -> Clip:
        job = self.store.get("jobs", clip.job_id)
        transcript = self.load_transcript(clip.job_id)
        campaign = self.campaign_for(job) if job else None
        clip.post_caption = self._caption(clip, transcript, campaign)
        clip.issues = check(campaign.requirements if campaign else None, clip.duration, clip.post_caption)
        self.store.put("clips", clip)
        return clip

    # ------------------------------------------------------------------ pipeline

    def _run(self, job: Job) -> None:
        ffmpeg.require_ffmpeg()
        jd = self.store.job_dir(job.id)
        campaign = self.campaign_for(job)
        req = campaign.requirements if campaign else None

        source = self.source_path(job.id)
        if source is None:
            if not job.source_url:
                raise RuntimeError("No video was uploaded for this job.")
            self._save(job, status="downloading", progress=0.0, message="Downloading video", error=None)
            source = ingest.download(job.source_url, jd, lambda p: self._save(job, progress=0.1 * p))
        info = ffmpeg.probe(source)
        if not info.has_audio:
            raise RuntimeError("This video has no sound, so there is nothing to transcribe.")
        self._save(job, source_duration=info.duration, error=None)

        transcript = self.load_transcript(job.id)
        wav = jd / "audio.wav"
        if transcript is None or not wav.exists():
            self._save(job, status="transcribing", progress=0.1, message="Listening to the video")
            ingest.extract_audio(source, wav)
            transcript = self.transcriber(
                wav, lambda p: self._save(job, progress=0.1 + 0.4 * p, message=f"Transcribing {int(p * 100)}%")
            )
            (jd / "transcript.json").write_text(transcript.model_dump_json())
        if not transcript.words:
            raise RuntimeError("No speech was found in this video.")
        energy = audio.loudness(wav)

        self._save(job, status="finding", progress=0.5, message="Finding the best moments")
        lo, hi = moments.length_limits(req)
        candidates, ai_problem = self._find_candidates(job, transcript, lo, hi, campaign)
        if not candidates:
            target = min(max(lo, 30.0), hi)
            candidates = moments.energy_candidates(energy, transcript.words, self.settings.max_clips * 2, target)
        final = moments.finalize(candidates, transcript.words, energy, lo, hi, self.settings.max_clips)
        if not final:
            raise RuntimeError("Couldn't find any clip-worthy moments in this video.")

        for old in self.store.clips_for_job(job.id):
            self.store.delete("clips", old.id)
        clips = [
            Clip(job_id=job.id, rank=i, start=c.start, end=c.end, score=int(c.score),
                 hook=c.hook or moments.excerpt(transcript.words, c.start, c.end, 6),
                 title=c.title, reason=c.reason)
            for i, c in enumerate(final)
        ]
        for clip in clips:
            self.store.put("clips", clip)

        self._save(job, status="rendering", progress=0.65, message=f"Editing {len(clips)} clips")
        for i, clip in enumerate(clips):
            self.render(clip, job, transcript=transcript, info=info, campaign=campaign)
            self._save(job, progress=0.65 + 0.35 * (i + 1) / len(clips), message=f"Edited {i + 1} of {len(clips)} clips")

        ready = sum(1 for c in self.store.clips_for_job(job.id) if c.render_status == "ready")
        message = f"{ready} clips ready"
        if ai_problem:
            message += f". AI picks unavailable ({ai_problem}), so these are the loudest moments."
        self._save(job, status="done", progress=1.0, message=message)

    def _find_candidates(self, job: Job, transcript: Transcript, lo: float, hi: float,
                         campaign: Campaign | None) -> tuple[list[moments.Candidate], str | None]:
        if self.brain.label == "offline":
            return [], "no Anthropic API key set"
        notes = campaign_notes(campaign)
        chunks = moments.windows(transcript.segments)
        found: list[moments.Candidate] = []
        problem = None
        for k, (a, b, segs) in enumerate(chunks):
            self._save(job, progress=0.5 + 0.15 * k / max(1, len(chunks)),
                       message=f"AI is watching part {k + 1} of {len(chunks)}")
            try:
                picks = self.brain.find_moments(moments.format_lines(segs), a, b, lo, hi, notes)
            except AIAuthError as e:
                return [], str(e)
            except AIError as e:
                log.warning("AI failed on chunk %s: %s", k, e)
                problem = str(e)
                continue
            found += [moments.Candidate(p.start, p.end, p.score, p.hook, p.title, p.reason, "ai") for p in picks]
        return found, (problem if not found else None)

    def _caption(self, clip: Clip, transcript: Transcript | None, campaign: Campaign | None) -> str:
        said = moments.excerpt(transcript.words, clip.start, clip.end, 80) if transcript else ""
        try:
            pc = self.brain.write_caption(clip.hook, said, campaign_notes(campaign))
        except AIError as e:
            log.warning("Caption generation failed: %s", e)
            pc = PostCaption(caption=clip.hook, hashtags=[])
        return build_post_caption(pc.caption, pc.hashtags, campaign.requirements if campaign else None)

    def render(self, clip: Clip, job: Job, transcript: Transcript | None = None,
               info: ffmpeg.MediaInfo | None = None, campaign: Campaign | None = None) -> Clip:
        jd = self.store.job_dir(job.id)
        clip.render_status, clip.error = "rendering", None
        self.store.put("clips", clip)
        try:
            source = self.source_path(job.id)
            if source is None:
                raise RuntimeError("The source video is gone; re-run the job.")
            transcript = transcript or self.load_transcript(job.id)
            info = info or ffmpeg.probe(source)
            campaign = campaign if campaign is not None else self.campaign_for(job)
            words = transcript.words if transcript else []

            intervals = silence.keep_intervals(words, clip.start, clip.end)
            min_seconds = campaign.requirements.min_seconds if campaign else None
            if min_seconds and silence.total_duration(intervals) < min_seconds:
                # Cutting pauses would make it too short for the campaign: keep the pauses.
                intervals = silence.keep_intervals([], clip.start, clip.end)
            duration = silence.total_duration(intervals)
            ass = jd / f"{clip.id}.ass"
            ass.write_text(build_ass(silence.remap_words(words, intervals), clip.hook, duration, CAPTION_FONT,
                                     clip.variant), encoding="utf-8")
            layout = plan_layout(source, info, clip.start, clip.end, self.finder())
            tmp = jd / f"{clip.id}.rendering.mp4"
            render_clip(source, info, intervals, layout, ass, tmp, clip.variant)
            os.replace(tmp, jd / f"{clip.id}.mp4")
            thumbnail(jd / f"{clip.id}.mp4", jd / f"{clip.id}.jpg")

            clip.duration = round(ffmpeg.probe(jd / f"{clip.id}.mp4").duration, 2)
            clip.layout = layout.mode
            if not clip.post_caption:
                clip.post_caption = self._caption(clip, transcript, campaign)
            clip.issues = check(campaign.requirements if campaign else None, clip.duration, clip.post_caption)
            clip.render_status = "ready"
        except Exception as e:
            log.exception("Render failed for clip %s", clip.id)
            clip.render_status, clip.error = "failed", str(e) or e.__class__.__name__
        clip.updated_at = now()
        self.store.put("clips", clip)
        return clip


def clip_paths(store: Store, clip: Clip) -> dict[str, Path]:
    jd = store.job_dir(clip.job_id)
    return {"video": jd / f"{clip.id}.mp4", "thumb": jd / f"{clip.id}.jpg"}
