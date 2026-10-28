"""Launch Windows Qt using only synthetic app content; no desktop capture, no API."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.settings import Settings
from app.repositories.db import Database


def main():
    report_dir = ROOT / "test-results"
    report_dir.mkdir(exist_ok=True)
    application = QApplication([])
    settings = Settings(data_dir=report_dir / "native-smoke-data")
    window = MainWindow(settings, Database(settings.data_dir / "copilot.sqlite3"))
    window.show()
    start = time.monotonic()
    state = {"stage": "ocr", "ok": False}

    def poll():
        if time.monotonic() - start > 30:
            state["error"] = "native GUI smoke timeout"
            timer.stop()
            application.quit()
        elif state["stage"] == "ocr" and window.ocr_table.rowCount():
            for row in range(window.ocr_table.rowCount()):
                if "首次连接" in window.ocr_table.item(row, 0).text():
                    window.use_ocr_line(row)
                    window.confirmed.setChecked(True)
                    window.generate_reply()
                    state["stage"] = "draft"
                    break
        elif state["stage"] == "draft" and window.conversation.draft:
            state["ok"] = "虚构演示" in window.reply.toPlainText()
            state["ocr_lines"] = window.ocr_table.rowCount()
            state["risk"] = window.conversation.draft.risk_level
            state["mode"] = window.conversation.draft.mode
            state["stage"] = "rendered"
            timer.stop()
            QTimer.singleShot(250, save_render)

    def save_render():
        # Capture only our synthetic QWidget, including scrollable content; never desktop.
        window.centralWidget().widget().grab().save(str(report_dir / "native-demo-window.png"))
        application.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    QTimer.singleShot(300, window.load_demo)
    application.exec()
    window.pool.waitForDone(5000)
    state["elapsed_seconds"] = round(time.monotonic()-start, 2)
    state["platform"] = application.platformName()
    (report_dir / "native-smoke.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False))
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
