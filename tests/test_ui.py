from threading import Event
from types import SimpleNamespace
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from app.models import OCRLine
from app.repositories.db import Database
from app.settings import Settings, ROOT
from app.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    win = MainWindow(Settings(data_dir=tmp_path), Database(tmp_path / "ui.db"))
    qtbot.addWidget(win)
    win.show()
    return win


def test_full_offline_ui_review_copy_and_edits(window, qtbot, monkeypatch):
    import httpx
    def deny(*args, **kwargs):
        raise AssertionError("Mock demo must not call network")
    monkeypatch.setattr(httpx.Client, "post", deny)
    window.ocr_service = SimpleNamespace(recognize=lambda image: [OCRLine(text="这个演示摄像头怎么首次连接？", confidence=.95, bbox=(10,10,500,50))])
    window.load_demo()
    qtbot.waitUntil(lambda: window.ocr_table.rowCount() == 1, timeout=5000)
    window.use_ocr_line(0)
    assert not window.generate_button.isEnabled()
    window.question.setPlainText("这个演示摄像头怎么首次连接？")
    window.confirmed.setChecked(True)
    assert window.generate_button.isEnabled()
    window.generate_button.click()
    qtbot.waitUntil(lambda: window.conversation.draft is not None, timeout=5000)
    assert "虚构演示" in window.reply.toPlainText()
    assert "demo_only" in window.sources.toPlainText()
    assert "example.com" not in window.reply.toPlainText()
    assert not window.copy_button.isEnabled()
    window.reviewed.setChecked(True)
    assert window.copy_button.isEnabled()
    window.copy_button.click()
    assert QApplication.clipboard().text() == window.reply.toPlainText()
    window.reply.insertPlainText("编辑")
    assert not window.reviewed.isChecked()
    window.reviewed.setChecked(True)
    window.question.setPlainText("换一个问题")
    assert not window.copy_button.isEnabled()
    assert window.conversation.draft.stale
    window.new_session()
    assert window.conversation.draft is None
    assert not window.reply.toPlainText() and not window.sources.toPlainText()


def test_late_worker_result_cannot_cross_session(window, qtbot):
    release = Event()
    results = []
    window.run_task(lambda: (release.wait(3), "old-customer")[1], results.append)
    window.new_session()
    release.set()
    qtbot.waitUntil(lambda: not window.workers, timeout=5000)
    assert results == []


def test_newer_request_wins(window, qtbot):
    release = Event()
    results = []
    window.run_task(lambda: (release.wait(3), "old")[1], results.append)
    window.run_task(lambda: "new", results.append)
    qtbot.waitUntil(lambda: results == ["new"], timeout=5000)
    release.set()
    qtbot.waitUntil(lambda: not window.workers, timeout=5000)
    assert results == ["new"]


def test_settings_and_knowledge_manager_construct(window, qtbot):
    from app.ui.settings_dialog import SettingsDialog
    from app.ui.knowledge_manager import KnowledgeManager
    settings = SettingsDialog(window.settings, window)
    qtbot.addWidget(settings)
    settings.enabled.setChecked(True)
    settings.save()
    assert "完整" in settings.error.text()
    assert not window.settings.ai_enabled
    manager = KnowledgeManager(window.db, window.settings.data_dir, window)
    qtbot.addWidget(manager)
    assert manager.products.count() == 2
    manager.documents.setCurrentRow(0)
    assert "虚构" in manager.doc_preview.toPlainText()
    manager.source_checked.setChecked(True)
    manager.source_reviewer.setText("测试审核员")
    manager.review_source()
    assert "演示" in manager.message.text()


def test_preview_cancellation_makes_no_request(window, qtbot, catalog_fixture, monkeypatch):
    from app.services.draft import prepare
    db, _, _, _, _, ctx = catalog_fixture
    window.settings.ai_enabled = True
    window.settings.ai_base_url = "https://fake-provider.test/v1"
    window.settings.ai_api_key = "fake"
    window.settings.ai_model = "fake"
    monkeypatch.setattr(window, "preview_payload", lambda payload: False)
    window._generate_prepared(ctx, prepare(db, ctx))
    assert not window.workers
    assert "取消" in window.status.text()
