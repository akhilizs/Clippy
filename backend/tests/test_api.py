"""Drives the HTTP API the way the iPhone app does, with fake transcription and AI."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import MomentPick, OfflineBrain, PostCaption
from app.main import create_app
from app.store import Store
from app.worker import Pipeline

from .conftest import make_transcript, needs_ffmpeg

TOKEN = "ABC123"


class FakeBrain(OfflineBrain):
    label = "fake-claude"

    def find_moments(self, transcript, chunk_start, chunk_end, lo, hi, campaign_notes):
        t = make_transcript()
        return [MomentPick(start=t.words[0].start, end=t.words[20].end, score=88, hook="Nobody talks about this",
                           title="Lost everything", reason="Strong confession hook")]

    def write_caption(self, hook, excerpt, campaign_notes):
        return PostCaption(caption="This changed everything", hashtags=["#story"])


def make_client(tmp_path, brain=None) -> tuple[TestClient, Pipeline]:
    settings = Settings(data_dir=tmp_path, anthropic_api_key=None, claude_model="fake", whisper_model="tiny",
                        access_token=TOKEN, max_clips=3, host="127.0.0.1", port=0)
    pipeline = Pipeline(Store(tmp_path), settings, brain=brain or FakeBrain(),
                        transcriber=lambda wav, cb: make_transcript(), face_finder=False)
    return TestClient(create_app(settings, pipeline)), pipeline


def wait_for(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}", headers={"X-Clippy-Token": TOKEN}).json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.3)
    pytest.fail("job did not finish")


def test_health_is_public_but_everything_else_needs_the_code(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/health").json()["ai"] == "fake-claude"
    assert client.get("/campaigns").status_code == 401
    assert client.get("/campaigns", headers={"X-Clippy-Token": "nope"}).status_code == 401
    assert client.get("/campaigns", headers={"X-Clippy-Token": TOKEN.lower()}).status_code == 200


def test_campaign_rules_are_parsed(tmp_path):
    client, _ = make_client(tmp_path)
    h = {"X-Clippy-Token": TOKEN}
    res = client.post("/campaigns", headers=h, json={
        "name": "Podcast clips", "rules_text": "Use #ad, tag @show. 20-60 seconds. $2 per 1k views."})
    camp = res.json()
    assert camp["requirements"]["required_hashtags"] == ["#ad"]
    assert camp["requirements"]["cpm_usd"] == 2.0
    assert [c["id"] for c in client.get("/campaigns", headers=h).json()] == [camp["id"]]


@needs_ffmpeg
def test_upload_to_rendered_clips_and_tracking(tmp_path, sample_video):
    client, _ = make_client(tmp_path)
    h = {"X-Clippy-Token": TOKEN}
    camp = client.post("/campaigns", headers=h, json={"name": "C", "rules_text": "Use #ad. $2 per 1k views"}).json()

    res = client.post(f"/jobs/upload?filename=my%20video.mov&campaign_id={camp['id']}", headers=h,
                      content=sample_video.read_bytes())
    assert res.status_code == 200, res.text
    job = wait_for(client, res.json()["id"])
    assert job["status"] == "done", job
    assert len(job["clips"]) == 1
    clip = job["clips"][0]
    assert clip["render_status"] == "ready" and clip["layout"] == "blur"
    assert clip["hook"] == "Nobody talks about this"
    assert "#ad" in clip["post_caption"] and "#story" in clip["post_caption"]
    assert not [i for i in clip["issues"] if i["level"] == "error"]

    video = client.get(f"/clips/{clip['id']}/video?token={TOKEN}", headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and len(video.content) == 100  # AVPlayer needs range requests
    assert client.get(f"/clips/{clip['id']}/thumbnail", headers=h).status_code == 200

    # Edit the hook -> re-render with the new text.
    edited = client.patch(f"/clips/{clip['id']}", headers=h, json={"hook": "He had ten seconds"}).json()
    assert edited["render_status"] in ("pending", "rendering", "ready")
    deadline = time.time() + 60
    while client.get(f"/clips/{clip['id']}", headers=h).json()["render_status"] != "ready":
        assert time.time() < deadline
        time.sleep(0.3)

    sub = client.post("/submissions", headers=h, json={"clip_id": clip["id"], "platform": "tiktok",
                                                       "url": "https://tiktok.com/@me/video/1", "views": 12000}).json()
    assert sub["campaign_id"] == camp["id"]
    assert sub["estimated_earnings_usd"] == 24.0
    sub = client.patch(f"/submissions/{sub['id']}", headers=h, json={"views": 50000}).json()
    assert sub["estimated_earnings_usd"] == 100.0 and len(sub["snapshots"]) == 2


@needs_ffmpeg
def test_offline_mode_falls_back_to_loudest_moments(tmp_path, sample_video):
    client, _ = make_client(tmp_path, brain=OfflineBrain())
    h = {"X-Clippy-Token": TOKEN}
    res = client.post("/jobs/upload?filename=a.mp4", headers=h, content=sample_video.read_bytes())
    job = wait_for(client, res.json()["id"])
    assert job["status"] == "done", job
    assert job["clips"] and "loudest" in job["message"]


@needs_ffmpeg
def test_clip_never_ends_up_shorter_than_campaign_minimum(tmp_path, sample_video):
    client, _ = make_client(tmp_path)
    h = {"X-Clippy-Token": TOKEN}
    camp = client.post("/campaigns", headers=h, json={"name": "C", "rules_text": "Clips must be 15-60 seconds"}).json()
    assert camp["requirements"]["min_seconds"] == 15
    res = client.post(f"/jobs/upload?filename=a.mp4&campaign_id={camp['id']}", headers=h,
                      content=sample_video.read_bytes())
    job = wait_for(client, res.json()["id"])
    assert job["status"] == "done", job
    clip = job["clips"][0]
    assert clip["duration"] >= 15
    assert not [i for i in clip["issues"] if i["level"] == "error"]


def test_bad_link_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    res = client.post("/jobs", headers={"X-Clippy-Token": TOKEN}, json={"source_url": "not a link"})
    assert res.status_code == 400
