from app.models import ConfirmedContext, OCRLine
from app.repositories.db import Database
from app.settings import Settings, load_yaml
import pytest


def test_default_offline_and_configuration():
    assert not Settings().online_ready
    assert load_yaml("rules.yaml")["privacy"]["send_raw_screenshot_to_model"] is False


def test_database_initialization_is_repeatable(tmp_path):
    db = Database(tmp_path / "demo.db")
    Database(db.path)
    assert db.rows("SELECT * FROM products") == []


def test_fingerprint_excludes_capture_time_but_includes_context():
    ctx = ConfirmedContext(session_local_id="one", latest_customer_message="问题")
    assert ctx.fingerprint == ctx.model_copy(update={"capture_id": "new"}).fingerprint
    assert ctx.fingerprint != ctx.model_copy(update={"sku": "sku"}).fingerprint


def test_ocr_contract():
    assert OCRLine(text="测试", bbox=(0, 0, 10, 10), confidence=.9).speaker == "unknown"
    with pytest.raises(ValueError):
        OCRLine(text="测试", bbox=(0, 0, 10, 10), confidence=2)


def test_start_window(qtbot, tmp_path):
    from app.ui.main_window import MainWindow
    win = MainWindow(Settings(data_dir=tmp_path), Database(tmp_path / "demo.db"))
    qtbot.addWidget(win)
    assert "客服" in win.windowTitle()
