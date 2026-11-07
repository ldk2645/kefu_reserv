from test_kbs import sample_raw, sample_product
from kbs_collector.storage import Storage
from kbs_collector.ui import CollectorWindow
from kbs_collector.policy import CollectorError


def test_collection_requires_manual_authorization(qtbot,tmp_path):
    window = CollectorWindow(Storage(tmp_path),fixture=True)
    qtbot.addWidget(window)
    assert not window.authorization.isChecked() and not window.login.isChecked()
    window.inspect()
    assert not window.workers
    assert "授权" in window.status.text()
    window.navigator = object()
    window.login.setChecked(True)
    window.inspect()
    assert not window.workers


def test_background_errors_are_sanitized_and_restrictions_pause(qtbot,tmp_path):
    window = CollectorWindow(Storage(tmp_path),fixture=True)
    qtbot.addWidget(window)
    def fail():
        raise RuntimeError("FICTIONAL_SECRET_MUST_NOT_LEAK")
    window.run(fail,lambda value:None)
    qtbot.waitUntil(lambda:not window.workers,timeout=5000)
    assert "FICTIONAL_SECRET" not in window.status.text()
    window.authorization.setChecked(True)
    window.login.setChecked(True)
    def restricted():
        raise CollectorError("ACCESS_RESTRICTED")
    window.run(restricted,lambda value:None)
    qtbot.waitUntil(lambda:not window.workers,timeout=5000)
    assert not window.login.isChecked() and not window.authorization.isChecked()


def test_capture_ui_preview_save_and_report(qtbot,tmp_path,sample_raw,sample_product):
    window = CollectorWindow(Storage(tmp_path),fixture=False)
    qtbot.addWidget(window)
    window.navigator = object()
    window.authorization.setChecked(True)
    window.login.setChecked(True)
    window.raw = sample_raw
    window.task_id = window.storage.begin({"source_url":sample_raw["source_url"]})
    for key,value in sample_product.model_dump(exclude={"is_demo"}).items():
        window.product_fields[key].setText(value)
    window.save_capture()
    assert not window.storage.captures()
    window.capture_checked.setChecked(True)
    window.save_capture()
    qtbot.waitUntil(lambda:not window.workers,timeout=5000)
    assert len(window.storage.captures()) == 1
    assert "成功 1" in window.status.text()
    assert str(tmp_path/"crawl_manifest.json") in window.status.text()
    assert window.raw is None and not window.capture_checked.isChecked()


def test_changes_revoke_manual_review(qtbot,tmp_path):
    window = CollectorWindow(Storage(tmp_path),fixture=True)
    qtbot.addWidget(window)
    window.capture_checked.setChecked(True)
    window.product_fields["model"].setText("DIFFERENT-FICTIONAL-MODEL")
    assert not window.capture_checked.isChecked()
    window.raw = {"fictional":True}
    window.roots.setCurrentText("#different-fixture-region")
    assert window.raw is None
    window.import_checked.setChecked(True)
    window.product_list.addItem("虚构新 SKU","fixture-id")
    assert not window.import_checked.isChecked()


def test_saved_preview_does_not_require_live_browser(qtbot,tmp_path,sample_raw,sample_product):
    from kbs_collector.normalizer import normalize
    store=Storage(tmp_path)
    store.save(normalize(sample_raw,sample_product),store.begin({'fixture':'preview'}))
    window=CollectorWindow(store)
    qtbot.addWidget(window)
    window.preview_saved()
    qtbot.waitUntil(lambda:not window.workers,timeout=5000)
    assert 'TEST-CAM-A' in window.preview.toPlainText()
    assert window.raw is None and not window.capture_checked.isChecked()
    assert window.browser.driver is None
