import json
import socket
import httpx
import pytest
from app.models import ModelReply
from app.services.draft import prepare, generate, build_payload, validate_model
from app.services.llm_client import LLMClient, ProviderError, SYSTEM_PROMPT
from app.settings import Settings


def online_settings():
    return Settings(ai_enabled=True, ai_base_url="https://model-fixture.test/v1", ai_api_key="fake-test-key",
                    ai_model="test-model", demo_mode=False, ai_timeout_seconds=2)


def model_reply(evidence, **changes):
    data = dict(intent="how_to_use", risk_level="R0", missing_information=[],
        customer_reply="您好，请打开测试设置页面，然后选择测试网络。", operator_note="测试",
        used_knowledge_ids=[evidence.hits[0].chunk_id], used_video_ids=[])
    data.update(changes)
    return ModelReply(**data)


def test_mock_disabled_has_zero_network(catalog_fixture, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Network access forbidden in mock mode")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(httpx.Client, "post", deny)
    db, _, _, _, _, ctx = catalog_fixture
    evidence = prepare(db, ctx)
    settings = online_settings()
    settings.ai_enabled = False
    assert "Mock" in generate(ctx, evidence, settings).mode
    settings.ai_enabled = True
    settings.ai_api_key = ""
    assert "Mock" in generate(ctx, evidence, settings).mode


def test_preview_required_and_actual_http_contract(catalog_fixture):
    db, _, _, _, _, ctx = catalog_fixture
    evidence = prepare(db, ctx)
    settings = online_settings()
    requests = []
    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
        assert body["messages"][1]["role"] == "user"
        assert "image" not in request.content.decode()
        assert "fake-test-key" not in request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": model_reply(evidence).model_dump_json()}}]})
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="预览"):
        generate(ctx, evidence, settings, client=client)
    assert not requests
    draft = generate(ctx, evidence, settings, payload=build_payload(ctx, evidence), client=client)
    assert "AI 回复" in draft.mode
    assert len(requests) == 1


@pytest.mark.parametrize("failure", ["timeout", "not_json", "wrong_schema", "server_error", "redirect"])
def test_api_failures_fallback_without_raw_error(catalog_fixture, failure):
    db, _, _, _, _, ctx = catalog_fixture
    evidence = prepare(db, ctx)
    settings = online_settings()
    requests = []
    def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("fake-test-key private-data", request=request)
        if failure == "server_error":
            return httpx.Response(500, text="private-data")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://unapproved.test"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "bad" if failure == "not_json" else '{"customer_reply":"fake-test-key"}'}}]})
    draft = generate(ctx, evidence, settings, build_payload(ctx, evidence),
                     LLMClient(settings, transport=httpx.MockTransport(handler)))
    assert "回退" in draft.operator_note
    assert "fake-test-key" not in draft.model_dump_json()
    assert "private-data" not in draft.model_dump_json()
    assert len(requests) == 1


@pytest.mark.parametrize("changes", [
    {"used_knowledge_ids": ["invented-id"]}, {"used_video_ids": ["invented-video"]},
    {"customer_reply": "去 https://unreviewed.test/video 看一下"}, {"customer_reply": "小鲸吃token了"},
    {"customer_reply": "长按复位键30秒"}, {"customer_reply": "给您赔偿500元"},
    {"customer_reply": "我已经查过您的订单"}, {"customer_reply": "视频里30秒演示了操作"},
    {"customer_reply": "这款支持无线充电和双频Wi-Fi"}, {"customer_reply": "请打开机壳拆机复位"},
    {"customer_reply": "教程地址：unreviewed.cn/video"},
])
def test_invalid_model_output_rejected(catalog_fixture, changes):
    db, _, _, _, _, ctx = catalog_fixture
    evidence = prepare(db, ctx)
    with pytest.raises(ValueError):
        validate_model(model_reply(evidence, **changes), evidence)


def test_high_risk_never_delegated_or_downgraded(catalog_fixture):
    db, _, _, _, _, ctx = catalog_fixture
    class BadClient:
        def generate(self, payload):
            raise AssertionError("R3 must be handled locally")
    ctx.latest_customer_message = "电池鼓包并冒烟"
    evidence = prepare(db, ctx)
    draft = generate(ctx, evidence, online_settings(), client=BadClient())
    assert draft.risk_level == "R3" and "停止" in draft.customer_reply


def test_model_higher_risk_is_preserved(catalog_fixture):
    db, _, _, _, _, ctx = catalog_fixture
    evidence = prepare(db, ctx)
    class HighRiskClient:
        def generate(self, payload):
            return model_reply(evidence, risk_level="R3")
    draft = generate(ctx, evidence, online_settings(), build_payload(ctx, evidence), HighRiskClient())
    assert draft.risk_level == "R3"
    assert "停止" in draft.customer_reply and "人工" in draft.customer_reply
