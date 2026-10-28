import json
import pytest
from app.services.redaction import redact
from app.services.draft import prepare, build_payload
from app.services.demo import seed_demo


def test_sensitive_fields_redacted():
    text = "姓名：张三，电话13800138000，订单123456789012345678，邮箱user@company.cn；地址：浙江省杭州市某街道88号1楼"
    result = redact(text)
    for secret in ["张三", "13800138000", "123456789012345678", "user@company.cn", "某街道", "杭州市"]:
        assert secret not in result


def test_preview_minimization_and_all_text_redacted(catalog_fixture):
    db, _, _, _, _, ctx = catalog_fixture
    ctx.latest_customer_message += "，电话13800138000"
    ctx.conversation_context = "订单123456789012345678；收件人：张三；地址：测试路88号"
    payload = build_payload(ctx, prepare(db, ctx))
    text = json.dumps(payload, ensure_ascii=False)
    for secret in ["13800138000", "123456789012345678", "张三", "测试路", "session_local_id", "capture_id", "source_url", "path"]:
        assert secret not in text
    assert "怎么连接测试网络" in text


def test_demo_is_never_sent(catalog_fixture, tmp_path):
    db, _, _, _, _, ctx = catalog_fixture
    seed_demo(db, tmp_path)
    ctx.product_id, ctx.sku = "DEMO-001", "SHOP-DEMO-01"
    with pytest.raises(ValueError, match="演示"):
        build_payload(ctx, prepare(db, ctx, True))


def test_chat_never_persisted(catalog_fixture):
    db, _, _, _, _, ctx = catalog_fixture
    ctx.latest_customer_message = "UniqueSyntheticCustomerMessage888"
    prepare(db, ctx)
    with db.connect() as conn:
        dump = "\n".join(conn.iterdump())
    assert "UniqueSyntheticCustomerMessage888" not in dump
