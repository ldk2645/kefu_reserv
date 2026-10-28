from app.repositories.catalog import Catalog
from app.services.document_import import import_document
from app.models import VideoSuggestion
from app.settings import ROOT


def seed_demo(db, data_dir):
    catalog = Catalog(db)
    if not catalog.product("DEMO-001"):
        catalog.add_product("演示品牌", "虚构演示摄像头", "DEMO-CAM-A", "SHOP-DEMO-01", "演示摄像头A",
                            "camera", True, "DEMO-001")
    if not catalog.product("DEMO-002"):
        catalog.add_product("演示品牌", "虚构演示耳机", "DEMO-EAR-B", "SHOP-DEMO-02", "演示耳机B",
                            "earbuds", True, "DEMO-002")
    if not db.rows("SELECT id FROM knowledge_sources WHERE product_id='DEMO-001'"):
        import_document(db, data_dir, ROOT / "samples/knowledge_demo_不可用于真实客服.md", "DEMO-001",
                        "internal_faq", "开发包内虚构数据，非官方资料")
    if not db.rows("SELECT video_id FROM video_links WHERE video_id='VID-DEMO-001'"):
        catalog.save_video(VideoSuggestion(video_id="VID-DEMO-001", product_id="DEMO-001", title="占位视频，禁止发送",
            url="https://example.com/demo-placeholder", intent_tags=["wifi_setup"], verified_status="pending",
            official_source_name="演示来源", official_source_url="https://example.com", is_demo=True))
