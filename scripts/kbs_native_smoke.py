"""Visible Qt + Chrome smoke on fictional local HTML only; never touches real KBS."""
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.pop("QT_QPA_PLATFORM",None)

from PySide6.QtCore import QTimer, QLockFile
from PySide6.QtWidgets import QApplication
from kbs_collector.demo import start_demo
from kbs_collector.policy import DATA
from kbs_collector.storage import Storage
from kbs_collector.ui import CollectorWindow


def main():
    app = QApplication([])
    DATA.mkdir(parents=True,exist_ok=True)
    lock = QLockFile(str(DATA/"collector.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        print("COLLECTOR_ALREADY_RUNNING")
        return 1
    server,url = start_demo()
    store = Storage(DATA/"demo_smoke"/uuid4().hex)
    window = CollectorWindow(store,"chrome",os.getenv("KBS_TEST_DRIVER"),url,fixture=True)
    window.show()
    state = {"stage":"opening","ok":False,"fixture_only":True}
    started = time.monotonic()
    report_dir = ROOT/"test-results"
    report_dir.mkdir(exist_ok=True)
    def poll():
        if time.monotonic()-started > 120:
            state["error"] = "TIMEOUT"
            timer.stop()
            window.shutdown = True
            window.close()
            return
        if window.workers:
            return
        if state["stage"] == "opening" and window.navigator:
            window.authorization.setChecked(True)
            window.login.setChecked(True)
            state["stage"] = "inspecting"
            window.inspect()
        elif state["stage"] == "inspecting" and window.frames.count() == 3:
            window.frames.setCurrentIndex(2)
            window.roots.setCurrentText("#demo-article")
            state["stage"] = "extracting"
            window.preview_capture()
        elif state["stage"] == "extracting" and window.raw:
            state["stage"] = "saving"
            window.capture_checked.setChecked(True)
            window.save_capture()
        elif state["stage"] == "saving" and store.captures():
            report = store.export()
            state.update(ok=report["success"]==1 and report["pending_review"]==1,
                success=report["success"],pending_review=report["pending_review"],stage="complete")
            # Only our QWidget containing fictional fixture data, never desktop/browser screenshots.
            window.grab().save(str(report_dir/"kbs-native-demo-window.png"))
            timer.stop()
            window.close()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    QTimer.singleShot(250,window.open_browser)
    try:
        app.exec()
        window.pool.waitForDone(45000)
    finally:
        window.browser.close()
        server.shutdown()
        server.server_close()
        lock.unlock()
    state.update(platform=app.platformName(),elapsed_seconds=round(time.monotonic()-started,2))
    (report_dir/"kbs-native-smoke.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(state,ensure_ascii=False))
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
