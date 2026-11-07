from threading import Event
from types import SimpleNamespace
import pytest
from PIL import Image

from app.models import OCRLine
from app.repositories.db import Database
from app.settings import Settings, ROOT
from app.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    copies=[]
    win = MainWindow(Settings(data_dir=tmp_path), Database(tmp_path / "ui.db"),clipboard_writer=copies.append)
    win.test_copies=copies
    qtbot.addWidget(win)
    win.show()
    return win


def test_full_offline_ui_review_copy_and_edits(window, qtbot, monkeypatch):
    import socket
    def deny(*args, **kwargs):
        raise AssertionError("Mock demo must not call network")
    monkeypatch.setattr(socket.socket, "connect", deny)
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
    assert window.test_copies == [window.reply.toPlainText()]
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
    assert not hasattr(settings,'enabled') and not hasattr(settings,'key')
    settings.save()
    assert not window.settings.online_ready
    assert (window.settings.data_dir/'preferences.json').exists()
    manager = KnowledgeManager(window.db, window.settings.data_dir, window)
    qtbot.addWidget(manager)
    assert manager.products.count() == 2
    manager.documents.setCurrentRow(0)
    assert "虚构" in manager.doc_preview.toPlainText()
    manager.source_checked.setChecked(True)
    manager.source_reviewer.setText("测试审核员")
    manager.review_source()
    assert "演示" in manager.message.text()


def test_ui_has_no_online_preview(window):
    assert not hasattr(window,'preview_payload')
    assert '离线' in window.banner.text()


@pytest.mark.parametrize('change',['source_withdrawn','product_changed','question_changed','session_changed'])
def test_real_mode_rechecks_before_copy(catalog_fixture,qtbot,tmp_path,change):
    db,catalog,product_a,product_b,source,_=catalog_fixture
    copies=[]
    win=MainWindow(Settings(data_dir=tmp_path,demo_mode=False),db,clipboard_writer=copies.append)
    qtbot.addWidget(win)
    win.product.setCurrentIndex(win.product.findData(product_a))
    win.question.setPlainText('怎么连接测试网络')
    win.confirmed.setChecked(True)
    win.generate_button.click()
    qtbot.waitUntil(lambda:not win.workers,timeout=5000)
    assert win.conversation.draft.used_knowledge_ids
    win.copy_reply()
    assert not copies
    win.reviewed.setChecked(True)
    win.copy_reply()
    assert len(copies)==1
    if change=='source_withdrawn':
        catalog.review_source(source,'deprecated','虚构审核员')
    elif change=='product_changed':
        win.product.setCurrentIndex(win.product.findData(product_b))
    elif change=='question_changed':
        win.question.setPlainText('虚构的新问题')
    else:
        win.new_session()
    win.copy_reply()
    assert len(copies)==1
