import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from app.repositories.db import Database
from app.repositories.catalog import Catalog
from app.services.document_import import import_document
from app.models import ConfirmedContext


@pytest.fixture
def catalog_fixture(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    catalog = Catalog(db)
    a = catalog.add_product("测试厂商", "自动化测试设备", "TEST-CAM-A", "SKU-A")
    b = catalog.add_product("测试厂商", "自动化测试设备", "TEST-CAM-A2", "SKU-B")
    manual = tmp_path / "test-manual.md"
    manual.write_text("# 首次连接\n\n连接测试设备时，打开测试设置页面，然后选择测试网络。", encoding="utf-8")
    source = import_document(db, tmp_path, manual, a, "official_manual", "仅用于自动化测试的虚构来源")
    catalog.review_source(source, "approved", "测试审核员")
    context = ConfirmedContext(session_local_id="test-session", confirmed_by_user=True,
        latest_customer_message="怎么连接测试网络", product_id=a, sku="SKU-A")
    return db, catalog, a, b, source, context
