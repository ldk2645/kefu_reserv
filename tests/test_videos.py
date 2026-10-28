import pytest
from app.models import VideoSuggestion
from app.services.video_links import find_videos, valid_public_url, video_intent
from app.services.draft import prepare, generate, review_copy
from app.settings import Settings


def add_video(catalog, product_id, **updates):
    # Synthetic metadata only; no request to this domain is performed by tests.
    data = dict(video_id="test-video", product_id=product_id, title="测试视频",
        url="https://training.vendor-fixture.cn/setup?model=A&version=1", intent_tags=["wifi_setup"],
        verified_status="approved", official_source_name="虚构测试厂商",
        official_source_url="https://vendor-fixture.cn/support", customer_shareable=True,
        verified_by="测试审核员", link_status="valid")
    data.update(updates)
    video = VideoSuggestion(**data)
    catalog.save_video(video)
    return video


def test_approved_video_exact_url_and_manual_removal(catalog_fixture):
    db, catalog, a, _, _, ctx = catalog_fixture
    video = add_video(catalog, a)
    evidence = prepare(db, ctx)
    assert evidence.videos[0].url == video.url
    draft = generate(ctx, evidence, Settings(demo_mode=False))
    assert video.url in draft.customer_reply
    assert review_copy(db, draft, ctx, draft.customer_reply, True, False) == draft.customer_reply
    edited = draft.customer_reply.replace("\n官方教程：" + video.url, "")
    assert video.url not in review_copy(db, draft, ctx, edited, True, False)
    video.link_status = "broken"
    video.verified_status = "pending"
    catalog.save_video(video)
    with pytest.raises(ValueError, match="URL"):
        review_copy(db, draft, ctx, draft.customer_reply, True, False)


@pytest.mark.parametrize("updates", [
    {"verified_status": "pending"}, {"verified_status": "rejected"}, {"verified_status": "deprecated"},
    {"verified_status": "pending", "link_status": "broken"},
    {"verified_status": "pending", "link_status": "unknown"},
    {"customer_shareable": False}, {"intent_tags": ["cleaning"]},
])
def test_video_filters(catalog_fixture, updates):
    db, catalog, a, _, _, ctx = catalog_fixture
    add_video(catalog, a, **updates)
    assert not find_videos(db, a, ctx.latest_customer_message)


def test_wrong_model_and_placeholder(catalog_fixture):
    db, catalog, a, b, _, ctx = catalog_fixture
    add_video(catalog, b)
    assert not find_videos(db, a, ctx.latest_customer_message)
    with pytest.raises(ValueError):
        add_video(catalog, a, url="https://example.com/demo")
    with pytest.raises(ValueError):
        add_video(catalog, a, link_status="unknown")


@pytest.mark.parametrize("url", ["http://vendor.cn/a", "https://example.com/a", "https://sub.example.com/a",
    "https://127.0.0.1/a", "https://localhost/a", "https://a.local/", "https://user:pass@vendor.cn/a", "https://vendor.cn/a\n"])
def test_url_validation(url):
    assert not valid_public_url(url)


def test_intent_is_not_only_product_category():
    assert video_intent("摄像头怎么清洁") == "cleaning"
    assert video_intent("耳机如何复位") == "reset"
    assert video_intent("摄像头的官方视频在哪") == "other"
