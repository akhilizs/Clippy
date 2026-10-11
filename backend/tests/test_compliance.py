from app.models import CampaignRequirements
from app.pipeline.compliance import build_post_caption, check

REQ = CampaignRequirements(
    required_hashtags=["#ad", "BrandClips"],
    required_mentions=["@brand"],
    credit_text="Credit: @brand on YouTube",
    min_seconds=15,
    max_seconds=60,
    banned=["no reuploads of full episodes"],
)


def test_caption_gets_every_requirement():
    caption = build_post_caption("He really said that", ["#podcast", "#ad"], REQ)
    assert "He really said that" in caption
    assert "#ad" in caption and "#BrandClips" in caption and "#podcast" in caption
    assert caption.count("#ad") == 1
    assert "@brand" in caption and "Credit: @brand on YouTube" in caption
    errors = [i for i in check(REQ, 30, caption) if i.level == "error"]
    assert errors == []


def test_check_flags_missing_items_and_length():
    issues = check(REQ, 75, "just a caption #adventure")
    messages = " | ".join(i.message for i in issues if i.level == "error")
    assert "#ad" in messages  # '#adventure' must not count as '#ad'
    assert "#BrandClips" in messages
    assert "@brand" in messages
    assert "maximum is 60s" in messages
    assert any(i.level == "warning" and "reuploads" in i.message for i in issues)


def test_no_campaign_means_no_issues():
    assert check(None, 10, "") == []
    assert build_post_caption("hello", ["fun"], None) == "hello\n#fun"
